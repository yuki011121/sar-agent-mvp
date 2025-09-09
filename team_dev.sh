#!/bin/bash

# 团队开发工具脚本
# 使用方法: ./team_dev.sh [command] [agent-name]

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 可用的Agent
AGENTS=("weather" "health" "photo-analysis" "interview" "logistics" "path-analysis")

show_help() {
    echo "👥 SAR团队开发工具"
    echo
    echo "使用方法:"
    echo "  $0 [command] [agent-name]"
    echo
    echo "命令:"
    echo "  setup [agent]     - 为指定Agent设置独立开发环境"
    echo "  dev [agent]       - 启动Agent的开发环境"
    echo "  test [agent]      - 测试指定Agent"
    echo "  build [agent]     - 构建Agent的Docker镜像"
    echo "  clean [agent]     - 清理Agent的开发环境"
    echo "  status [agent]    - 查看Agent开发环境状态"
    echo "  logs [agent]      - 查看Agent日志"
    echo "  shell [agent]     - 进入Agent开发容器"
    echo
    echo "全局命令:"
    echo "  setup-all         - 为所有Agent设置开发环境"
    echo "  status-all        - 查看所有Agent状态"
    echo "  clean-all         - 清理所有开发环境"
    echo
    echo "示例:"
    echo "  $0 setup weather           # 设置Weather Agent开发环境"
    echo "  $0 dev weather             # 启动Weather Agent开发"
    echo "  $0 test weather            # 测试Weather Agent"
    echo "  $0 shell weather           # 进入Weather Agent容器"
}

validate_agent() {
    local agent=$1
    if [[ ! " ${AGENTS[@]} " =~ " ${agent} " ]]; then
        log_error "未知Agent: $agent"
        log_info "可用Agent: ${AGENTS[*]}"
        exit 1
    fi
}

setup_agent_dev_env() {
    local agent=$1
    validate_agent "$agent"
    
    log_info "为 $agent 设置独立开发环境..."
    
    local agent_dir="agents/$agent"
    
    # 检查Agent目录是否存在
    if [ ! -d "$agent_dir" ]; then
        log_error "Agent目录不存在: $agent_dir"
        exit 1
    fi
    
    cd "$agent_dir"
    
    # 创建独立的Dockerfile (如果不存在)
    if [ ! -f "Dockerfile" ]; then
        log_info "创建 $agent 的独立Dockerfile..."
        create_agent_dockerfile "$agent"
    fi
    
    # 创建独立的docker-compose.dev.yml (如果不存在)
    if [ ! -f "docker-compose.dev.yml" ]; then
        log_info "创建 $agent 的开发环境配置..."
        create_agent_compose "$agent"
    fi
    
    # 创建requirements.txt (如果不存在)
    if [ ! -f "requirements.txt" ]; then
        log_info "创建 $agent 的依赖文件..."
        create_agent_requirements "$agent"
    fi
    
    # 创建开发脚本
    if [ ! -f "dev.sh" ]; then
        log_info "创建 $agent 的开发脚本..."
        create_agent_dev_script "$agent"
        chmod +x dev.sh
    fi
    
    cd - > /dev/null
    
    log_success "$agent Agent开发环境设置完成"
    log_info "进入目录: cd agents/$agent"
    log_info "启动开发: ./dev.sh start"
}

create_agent_dockerfile() {
    local agent=$1
    
    cat > Dockerfile << EOF
# $agent Agent 独立Docker配置
FROM python:3.10-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

# 复制requirements
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制共享模块
COPY ../../shared ./shared

# 复制Agent代码
COPY . ./agents/$agent

# 设置环境变量
ENV PYTHONPATH=/app
ENV AGENT_NAME=$agent-agent

# 运行Agent
CMD ["python", "agents/$agent/main.py"]
EOF
}

create_agent_compose() {
    local agent=$1
    local port=$((6380 + $(printf '%s\n' "${AGENTS[@]}" | grep -n "^$agent$" | cut -d: -f1)))
    
    cat > docker-compose.dev.yml << EOF
# $agent Agent 独立开发环境
version: "3.9"

networks:
  $agent-dev:
    driver: bridge

services:
  redis-$agent:
    image: redis:7-alpine
    container_name: $agent-redis-dev
    ports: 
      - "$port:6379"
    command: ["redis-server", "--appendonly", "no"]
    networks:
      - $agent-dev
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3

  $agent-agent:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: $agent-agent-dev
    environment:
      - REDIS_URL=redis://redis-$agent:6379
      - LOG_LEVEL=DEBUG
    volumes:
      - ./:/app/agents/$agent
      - ../../shared:/app/shared
    depends_on:
      redis-$agent:
        condition: service_healthy
    networks:
      - $agent-dev
    restart: unless-stopped

  $agent-dev:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: $agent-dev-tools
    environment:
      - REDIS_URL=redis://redis-$agent:6379
    volumes:
      - ./:/app/agents/$agent
      - ../../shared:/app/shared
    command: sleep infinity
    depends_on:
      - redis-$agent
    networks:
      - $agent-dev
EOF
}

create_agent_requirements() {
    local agent=$1
    
    # 基础依赖
    cat > requirements.txt << EOF
# $agent Agent 专用依赖
redis>=6.2.0
python-dotenv>=1.0.0
requests>=2.32.4
EOF
    
    # 根据Agent类型添加特定依赖
    case $agent in
        "health")
            cat >> requirements.txt << EOF

# Health Agent 特定依赖
google-generativeai>=0.8.5
pydantic>=2.6.0
EOF
            ;;
        "photo-analysis")
            cat >> requirements.txt << EOF

# Photo Analysis Agent 特定依赖
ultralytics>=8.1.0
pillow>=10.0.0
opencv-python>=4.8.0
numpy>=1.24.0
face-recognition>=1.3.0
scikit-learn>=1.7.1
EOF
            ;;
        "interview")
            cat >> requirements.txt << EOF

# Interview Agent 特定依赖
openai>=1.95.1
PyPDF2>=3.0.0
EOF
            ;;
        "path-analysis")
            cat >> requirements.txt << EOF

# Path Analysis Agent 特定依赖
google-generativeai>=0.8.5
osmnx>=2.0.5
scipy>=1.11
numpy>=1.24.0
EOF
            ;;
        "logistics")
            cat >> requirements.txt << EOF

# Logistics Agent 特定依赖
google-generativeai>=0.8.5
EOF
            ;;
    esac
}

create_agent_dev_script() {
    local agent=$1
    
    cat > dev.sh << 'EOF'
#!/bin/bash

# Agent开发脚本

set -e

AGENT_NAME=$(basename $(pwd))

case $1 in
    "start")
        echo "🚀 启动 $AGENT_NAME 开发环境..."
        docker-compose -f docker-compose.dev.yml up -d
        echo "✅ 开发环境已启动"
        echo "💡 使用 './dev.sh logs' 查看日志"
        echo "💡 使用 './dev.sh shell' 进入容器"
        ;;
    "stop")
        echo "🛑 停止 $AGENT_NAME 开发环境..."
        docker-compose -f docker-compose.dev.yml down
        ;;
    "build")
        echo "🔨 构建 $AGENT_NAME Docker镜像..."
        docker-compose -f docker-compose.dev.yml build
        ;;
    "logs")
        docker-compose -f docker-compose.dev.yml logs -f
        ;;
    "shell")
        docker-compose -f docker-compose.dev.yml exec ${AGENT_NAME}-dev bash
        ;;
    "test")
        echo "🧪 测试 $AGENT_NAME..."
        docker-compose -f docker-compose.dev.yml exec ${AGENT_NAME}-dev python agents/${AGENT_NAME}/main.py
        ;;
    "status")
        docker-compose -f docker-compose.dev.yml ps
        ;;
    "clean")
        echo "🧹 清理 $AGENT_NAME 开发环境..."
        docker-compose -f docker-compose.dev.yml down -v
        docker-compose -f docker-compose.dev.yml rm -f
        ;;
    *)
        echo "使用方法: $0 {start|stop|build|logs|shell|test|status|clean}"
        ;;
esac
EOF
}

start_agent_dev() {
    local agent=$1
    validate_agent "$agent"
    
    log_info "启动 $agent Agent开发环境..."
    
    cd "agents/$agent"
    
    if [ ! -f "docker-compose.dev.yml" ]; then
        log_error "开发环境配置不存在，请先运行: ./team_dev.sh setup $agent"
        exit 1
    fi
    
    docker-compose -f docker-compose.dev.yml up -d
    
    log_success "$agent Agent开发环境已启动"
    log_info "查看日志: ./team_dev.sh logs $agent"
    log_info "进入容器: ./team_dev.sh shell $agent"
    
    cd - > /dev/null
}

# 主函数
main() {
    local command=${1:-help}
    local agent=$2
    
    case $command in
        "setup")
            if [ -z "$agent" ]; then
                log_error "请指定Agent名称"
                show_help
                exit 1
            fi
            setup_agent_dev_env "$agent"
            ;;
        "dev")
            if [ -z "$agent" ]; then
                log_error "请指定Agent名称"
                exit 1
            fi
            start_agent_dev "$agent"
            ;;
        "setup-all")
            for agent in "${AGENTS[@]}"; do
                setup_agent_dev_env "$agent"
            done
            ;;
        "status-all")
            for agent in "${AGENTS[@]}"; do
                if [ -f "agents/$agent/docker-compose.dev.yml" ]; then
                    echo "=== $agent Agent ==="
                    cd "agents/$agent"
                    docker-compose -f docker-compose.dev.yml ps
                    cd - > /dev/null
                    echo
                fi
            done
            ;;
        "clean-all")
            for agent in "${AGENTS[@]}"; do
                if [ -f "agents/$agent/docker-compose.dev.yml" ]; then
                    log_info "清理 $agent Agent..."
                    cd "agents/$agent"
                    docker-compose -f docker-compose.dev.yml down -v
                    cd - > /dev/null
                fi
            done
            ;;
        "test"|"build"|"clean"|"status"|"logs"|"shell")
            if [ -z "$agent" ]; then
                log_error "请指定Agent名称"
                exit 1
            fi
            validate_agent "$agent"
            cd "agents/$agent"
            if [ -f "dev.sh" ]; then
                ./dev.sh "$command"
            else
                log_error "开发脚本不存在，请先运行: ./team_dev.sh setup $agent"
            fi
            cd - > /dev/null
            ;;
        "help"|"-h"|"--help")
            show_help
            ;;
        *)
            log_error "未知命令: $command"
            show_help
            exit 1
            ;;
    esac
}

main "$@"
EOF

chmod +x team_dev.sh