#!/bin/bash

# SAR Multi-Agent System 快速启动脚本
# 使用方法: ./start_sar_system.sh [模式]
# 模式: full, minimal, dev, stop

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查Docker和Docker Compose
check_prerequisites() {
    log_info "检查系统依赖..."
    
    if ! command -v docker &> /dev/null; then
        log_error "Docker未安装，请先安装Docker"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose未安装，请先安装Docker Compose"
        exit 1
    fi
    
    log_success "系统依赖检查通过"
}

# 检查环境变量配置
check_environment() {
    log_info "检查环境配置..."
    
    if [ ! -f .env ]; then
        if [ -f .env.template ]; then
            log_warning ".env文件不存在，正在从模板创建..."
            cp .env.template .env
            log_warning "请编辑 .env 文件并填入你的API密钥"
            log_info "必需的API密钥:"
            log_info "  - OPENAI_API_KEY (用于Interview Agent)"
            log_info "  - GEMINI_API_KEY (用于Health/Path/Logistics Agents)"
            echo
            read -p "是否现在编辑 .env 文件? (y/n): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                ${EDITOR:-nano} .env
            else
                log_warning "请手动编辑 .env 文件后再次运行此脚本"
                exit 1
            fi
        else
            log_error ".env.template文件不存在"
            exit 1
        fi
    fi
    
    # 检查关键API密钥
    source .env 2>/dev/null || true
    
    if [ -z "$OPENAI_API_KEY" ] && [ -z "$GEMINI_API_KEY" ]; then
        log_error "至少需要配置 OPENAI_API_KEY 或 GEMINI_API_KEY 中的一个"
        exit 1
    fi
    
    log_success "环境配置检查通过"
}

# 启动基础设施
start_infrastructure() {
    log_info "启动基础设施服务 (Redis + MinIO)..."
    
    docker-compose up -d redis minio
    
    log_info "等待服务就绪..."
    sleep 10
    
    # 检查Redis
    if docker-compose exec -T redis redis-cli ping | grep -q "PONG"; then
        log_success "Redis服务就绪"
    else
        log_error "Redis服务启动失败"
        exit 1
    fi
    
    # 检查MinIO
    if curl -s http://localhost:9000/minio/health/live > /dev/null 2>&1; then
        log_success "MinIO服务就绪"
    else
        log_warning "MinIO服务可能还未完全就绪"
    fi
}

# 完整模式启动
start_full_mode() {
    log_info "启动完整SAR系统..."
    
    start_infrastructure
    
    log_info "启动所有Agent服务..."
    docker-compose up -d weather-agent health-agent photo-analysis-agent logistics-agent
    
    log_info "运行一次性Agent..."
    docker-compose run --rm interview-agent &
    docker-compose run --rm path-analysis-agent &
    
    wait
    
    log_success "完整SAR系统启动完成"
    show_status
}

# 最小模式启动
start_minimal_mode() {
    log_info "启动最小SAR系统..."
    
    start_infrastructure
    
    log_info "启动核心Agent服务..."
    docker-compose up -d weather-agent health-agent
    
    log_success "最小SAR系统启动完成"
    show_status
}

# 开发模式启动
start_dev_mode() {
    log_info "启动开发模式..."
    
    start_infrastructure
    
    log_info "启动开发容器..."
    docker-compose up -d dev
    
    log_success "开发环境启动完成"
    log_info "使用以下命令进入开发容器:"
    log_info "  docker-compose exec dev bash"
}

# 停止系统
stop_system() {
    log_info "停止SAR系统..."
    
    docker-compose down
    
    log_success "SAR系统已停止"
}

# 显示系统状态
show_status() {
    echo
    log_info "=== SAR系统状态 ==="
    docker-compose ps
    
    echo
    log_info "=== 可用服务端点 ==="
    log_info "Redis: localhost:6379"
    log_info "MinIO管理界面: http://localhost:9001 (用户名: minioadmin, 密码: minioadmin)"
    log_info "Redis管理界面 (可选): docker-compose --profile tools up -d redis-commander"
    log_info "                     访问: http://localhost:8081"
    
    echo
    log_info "=== 有用的命令 ==="
    log_info "查看所有日志: docker-compose logs"
    log_info "查看特定Agent日志: docker-compose logs -f <agent-name>"
    log_info "重启Agent: docker-compose restart <agent-name>"
    log_info "停止系统: docker-compose down"
    
    echo
    log_info "=== 测试系统 ==="
    log_info "测试图片分析: cp input_images/basketball.png input_images/test.png"
    log_info "查看Redis数据: docker-compose exec redis redis-cli"
    log_info "进入开发容器: docker-compose exec dev bash"
}

# 显示帮助
show_help() {
    echo "SAR Multi-Agent System 启动脚本"
    echo
    echo "使用方法:"
    echo "  $0 [模式]"
    echo
    echo "可用模式:"
    echo "  full     - 启动完整系统 (所有Agent)"
    echo "  minimal  - 启动最小系统 (核心Agent)"
    echo "  dev      - 启动开发环境"
    echo "  stop     - 停止系统"
    echo "  status   - 显示系统状态"
    echo "  help     - 显示此帮助信息"
    echo
    echo "示例:"
    echo "  $0 full      # 启动完整系统"
    echo "  $0 minimal   # 启动最小系统"
    echo "  $0 dev       # 启动开发环境"
    echo "  $0 stop      # 停止系统"
}

# 主函数
main() {
    local mode=${1:-full}
    
    case $mode in
        "full")
            check_prerequisites
            check_environment
            start_full_mode
            ;;
        "minimal")
            check_prerequisites
            check_environment
            start_minimal_mode
            ;;
        "dev")
            check_prerequisites
            check_environment
            start_dev_mode
            ;;
        "stop")
            stop_system
            ;;
        "status")
            show_status
            ;;
        "help"|"-h"|"--help")
            show_help
            ;;
        *)
            log_error "未知模式: $mode"
            show_help
            exit 1
            ;;
    esac
}

# 运行主函数
main "$@"