#!/bin/bash

# 单Agent测试脚本
# 使用方法: ./test_single_agent.sh [agent-name]

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# 可用的Agent列表
AVAILABLE_AGENTS=(
    "weather"
    "health" 
    "photo-analysis"
    "interview"
    "logistics"
    "path-analysis"
)

# 显示帮助
show_help() {
    echo "🧪 单Agent测试工具"
    echo
    echo "使用方法:"
    echo "  $0 [agent-name]"
    echo
    echo "可用的Agent:"
    for agent in "${AVAILABLE_AGENTS[@]}"; do
        echo "  - $agent"
    done
    echo
    echo "特殊命令:"
    echo "  list     - 显示所有可用Agent"
    echo "  setup    - 设置测试环境"
    echo "  cleanup  - 清理测试环境"
    echo "  redis    - 启动Redis并查看数据"
    echo
    echo "示例:"
    echo "  $0 setup           # 首次使用，设置环境"
    echo "  $0 weather         # 测试Weather Agent"
    echo "  $0 photo-analysis  # 测试Photo Analysis Agent"
    echo "  $0 redis           # 查看Redis中的数据"
}

# 检查环境
check_environment() {
    log_info "检查测试环境..."
    
    if [ ! -f .env ]; then
        log_warning ".env文件不存在，正在从模板创建..."
        cp .env.template .env
        log_warning "请编辑 .env 文件并填入你的API密钥"
        return 1
    fi
    
    source .env 2>/dev/null || true
    
    if [ -z "$OPENAI_API_KEY" ] && [ -z "$GEMINI_API_KEY" ]; then
        log_error "至少需要配置 OPENAI_API_KEY 或 GEMINI_API_KEY 中的一个"
        return 1
    fi
    
    log_success "环境检查通过"
    return 0
}

# 设置测试环境
setup_test_environment() {
    log_info "设置测试环境..."
    
    # 检查环境配置
    if ! check_environment; then
        log_error "环境配置失败，请先配置 .env 文件"
        return 1
    fi
    
    # 构建测试镜像
    log_info "构建Docker镜像..."
    docker-compose -f docker-compose.test.yml build
    
    # 启动Redis
    log_info "启动测试Redis..."
    docker-compose -f docker-compose.test.yml up -d redis-test
    
    # 等待Redis就绪
    log_info "等待Redis就绪..."
    sleep 5
    
    # 检查Redis连接
    if docker-compose -f docker-compose.test.yml exec -T redis-test redis-cli ping | grep -q "PONG"; then
        log_success "Redis测试环境就绪"
    else
        log_error "Redis启动失败"
        return 1
    fi
    
    # 启动测试容器
    log_info "启动测试容器..."
    docker-compose -f docker-compose.test.yml up -d test-env
    
    log_success "测试环境设置完成"
    log_info "Redis端口: localhost:6380"
    log_info "进入测试容器: docker-compose -f docker-compose.test.yml exec test-env bash"
}

# 清理测试环境
cleanup_test_environment() {
    log_info "清理测试环境..."
    docker-compose -f docker-compose.test.yml down -v
    log_success "测试环境已清理"
}

# 测试Weather Agent
test_weather_agent() {
    log_info "🌤️  测试Weather Agent..."
    
    log_info "启动Weather Agent..."
    docker-compose -f docker-compose.test.yml exec -d test-env python agents/weather/main.py
    
    log_info "等待30秒让Agent获取天气数据..."
    sleep 30
    
    log_info "检查Redis中的天气数据..."
    docker-compose -f docker-compose.test.yml exec test-env python -c "
import redis
import json
r = redis.Redis(host='redis-test', port=6379, decode_responses=True)
try:
    streams = r.keys('weather*')
    print(f'找到天气数据流: {streams}')
    for stream in streams:
        length = r.xlen(stream)
        print(f'流 {stream} 包含 {length} 条消息')
        if length > 0:
            messages = r.xrevrange(stream, count=1)
            if messages:
                print('最新消息:')
                msg_id, data = messages[0]
                for key, value in data.items():
                    try:
                        parsed = json.loads(value)
                        print(json.dumps(parsed, indent=2, ensure_ascii=False))
                    except:
                        print(f'{key}: {value}')
except Exception as e:
    print(f'错误: {e}')
"
    
    log_success "Weather Agent测试完成"
}

# 测试Health Agent
test_health_agent() {
    log_info "🏥 测试Health Agent..."
    
    # 首先添加一些模拟任务数据
    log_info "添加模拟任务数据..."
    docker-compose -f docker-compose.test.yml exec test-env python -c "
import redis
import json
from datetime import datetime, timezone

r = redis.Redis(host='redis-test', port=6379, decode_responses=True)

# 添加模拟任务数据
mission_data = {
    'person': {
        'name': 'John Doe',
        'age': 45,
        'gender': 'male',
        'known_conditions': ['diabetes type 2', 'recent back injury'],
        'clothing': 'light jacket, jeans, hiking boots',
        'time_missing': '36 hours',
        'last_seen': 'mountain trail near summit'
    },
    'timestamp': datetime.now(timezone.utc).isoformat()
}

r.xadd('mission.new', {'body': json.dumps({'payload': mission_data})})
print('已添加模拟任务数据')
"
    
    log_info "启动Health Agent (运行1分钟)..."
    timeout 60 docker-compose -f docker-compose.test.yml exec test-env python agents/health/main.py || true
    
    log_info "检查健康评估结果..."
    docker-compose -f docker-compose.test.yml exec test-env python -c "
import redis
import json
r = redis.Redis(host='redis-test', port=6379, decode_responses=True)
try:
    streams = r.keys('health*')
    print(f'找到健康评估流: {streams}')
    for stream in streams:
        length = r.xlen(stream)
        print(f'流 {stream} 包含 {length} 条消息')
        if length > 0:
            messages = r.xrevrange(stream, count=1)
            if messages:
                print('最新健康评估:')
                msg_id, data = messages[0]
                for key, value in data.items():
                    try:
                        parsed = json.loads(value)
                        print(json.dumps(parsed, indent=2, ensure_ascii=False))
                    except:
                        print(f'{key}: {value}')
except Exception as e:
    print(f'错误: {e}')
"
    
    log_success "Health Agent测试完成"
}

# 测试Photo Analysis Agent
test_photo_analysis_agent() {
    log_info "📸 测试Photo Analysis Agent..."
    
    # 检查测试图片
    if [ ! -d "input_images" ] || [ -z "$(ls -A input_images 2>/dev/null)" ]; then
        log_warning "input_images目录为空，创建测试图片..."
        mkdir -p input_images
        # 复制现有图片作为测试
        if [ -f "input_images/basketball.png" ]; then
            cp input_images/basketball.png input_images/test_photo.png
            log_info "已创建测试图片: input_images/test_photo.png"
        else
            log_warning "没有找到测试图片，请手动添加图片到 input_images/ 目录"
            return 1
        fi
    fi
    
    log_info "启动Photo Analysis Agent (运行30秒)..."
    timeout 30 docker-compose -f docker-compose.test.yml exec test-env python agents/photo_analysis/main.py || true
    
    log_info "检查图片分析结果..."
    docker-compose -f docker-compose.test.yml exec test-env python -c "
import redis
import json
r = redis.Redis(host='redis-test', port=6379, decode_responses=True)
try:
    streams = r.keys('photo*')
    print(f'找到图片分析流: {streams}')
    for stream in streams:
        length = r.xlen(stream)
        print(f'流 {stream} 包含 {length} 条消息')
        if length > 0:
            messages = r.xrevrange(stream, count=1)
            if messages:
                print('最新分析结果:')
                msg_id, data = messages[0]
                for key, value in data.items():
                    try:
                        parsed = json.loads(value)
                        # 只显示关键信息，避免输出过长
                        if 'detections' in parsed:
                            print(f'检测到 {len(parsed[\"detections\"])} 个对象')
                            for det in parsed['detections'][:3]:  # 只显示前3个
                                print(f'  - {det.get(\"class\", \"unknown\")}: {det.get(\"confidence\", 0):.2f}')
                        if 'person_analysis' in parsed:
                            pa = parsed['person_analysis']
                            print(f'人员分析: {pa.get(\"total_people\", 0)} 人, {pa.get(\"faces_detected\", 0)} 张脸')
                    except Exception as e:
                        print(f'解析错误: {e}')
                        print(f'{key}: {value[:100]}...')
except Exception as e:
    print(f'错误: {e}')
"
    
    log_success "Photo Analysis Agent测试完成"
}

# 测试Interview Agent
test_interview_agent() {
    log_info "🎤 测试Interview Agent..."
    
    # 检查是否有测试PDF
    if [ ! -d "data/transcripts" ] || [ -z "$(ls -A data/transcripts/*.pdf 2>/dev/null)" ]; then
        log_warning "没有找到访谈记录PDF文件"
        log_info "请将PDF文件放到 data/transcripts/ 目录中"
        log_info "或者我们可以测试Agent的其他功能..."
        
        # 测试Agent的基本功能
        docker-compose -f docker-compose.test.yml exec test-env python -c "
import sys
sys.path.append('/workspace')
from agents.interview.main import InterviewAnalystAgent

print('测试Interview Agent基本功能...')
agent = InterviewAnalystAgent(
    name='Test Interview Analyst',
    role='Test role',
    system_message='Test system message'
)

# 测试置信度评估
test_text = 'I think I saw someone near the trail, but I am not sure about the time.'
result = agent.assign_confidence_rating(test_text)
print(f'置信度评估结果: {result}')

# 测试实体提取（使用启发式方法）
sections = [test_text]
entities = agent._extract_entities_heuristic(test_text)
print(f'实体提取结果: {entities}')

print('Interview Agent基本功能测试完成')
"
        return 0
    fi
    
    log_info "运行Interview Agent..."
    docker-compose -f docker-compose.test.yml exec test-env python agents/interview/main.py
    
    log_success "Interview Agent测试完成"
}

# 测试Logistics Agent
test_logistics_agent() {
    log_info "📦 测试Logistics Agent..."
    
    log_info "启动Logistics Agent (运行30秒)..."
    timeout 30 docker-compose -f docker-compose.test.yml exec test-env python agents/logistics/main.py || true
    
    log_info "检查后勤请求数据..."
    docker-compose -f docker-compose.test.yml exec test-env python -c "
import redis
import json
r = redis.Redis(host='redis-test', port=6379, decode_responses=True)
try:
    streams = r.keys('logistics*')
    print(f'找到后勤数据流: {streams}')
    for stream in streams:
        length = r.xlen(stream)
        print(f'流 {stream} 包含 {length} 条消息')
        if length > 0:
            messages = r.xrevrange(stream, count=3)  # 显示最近3条
            for i, (msg_id, data) in enumerate(messages):
                print(f'消息 {i+1}:')
                for key, value in data.items():
                    try:
                        parsed = json.loads(value)
                        print(json.dumps(parsed, indent=2, ensure_ascii=False))
                    except:
                        print(f'{key}: {value}')
                print('---')
except Exception as e:
    print(f'错误: {e}')
"
    
    log_success "Logistics Agent测试完成"
}

# 测试Path Analysis Agent
test_path_analysis_agent() {
    log_info "🗺️  测试Path Analysis Agent..."
    
    # 检查DEM数据文件
    if [ ! -f "agents/path_analysis/data/slo_dem.tif" ]; then
        log_warning "DEM地形数据文件不存在，Path Analysis Agent可能无法正常运行"
        log_info "请确保 agents/path_analysis/data/slo_dem.tif 文件存在"
    fi
    
    log_info "运行Path Analysis Agent..."
    docker-compose -f docker-compose.test.yml exec test-env python agents/path_analysis/main.py || {
        log_warning "Path Analysis Agent运行出错，可能是缺少DEM数据或依赖"
        return 0
    }
    
    log_info "检查路径分析结果..."
    docker-compose -f docker-compose.test.yml exec test-env python -c "
import redis
import json
r = redis.Redis(host='redis-test', port=6379, decode_responses=True)
try:
    streams = r.keys('path*')
    print(f'找到路径分析流: {streams}')
    for stream in streams:
        length = r.xlen(stream)
        print(f'流 {stream} 包含 {length} 条消息')
        if length > 0:
            messages = r.xrevrange(stream, count=1)
            if messages:
                print('路径分析结果概要:')
                msg_id, data = messages[0]
                for key, value in data.items():
                    try:
                        parsed = json.loads(value)
                        if 'results' in parsed:
                            results = parsed['results']
                            print(f'分析了 {len(results)} 条路径')
                            for i, path in enumerate(results[:3]):  # 只显示前3条
                                print(f'  路径 {i+1}: {path.get(\"summary\", \"无摘要\")}')
                    except Exception as e:
                        print(f'解析结果时出错: {e}')
except Exception as e:
    print(f'错误: {e}')
"
    
    log_success "Path Analysis Agent测试完成"
}

# 查看Redis数据
view_redis_data() {
    log_info "📊 查看Redis中的数据..."
    
    docker-compose -f docker-compose.test.yml exec test-env python -c "
import redis
import json
from datetime import datetime

r = redis.Redis(host='redis-test', port=6379, decode_responses=True)

print('=== Redis数据概览 ===')
try:
    # 获取所有流
    streams = r.keys('*')
    if not streams:
        print('❌ Redis中没有数据')
        return
    
    print(f'📡 找到 {len(streams)} 个数据流:')
    
    for stream in sorted(streams):
        try:
            if stream.endswith('.raw') or 'mission' in stream:
                length = r.xlen(stream)
                print(f'\\n📋 {stream}: {length} 条消息')
                
                if length > 0:
                    # 获取最新消息
                    messages = r.xrevrange(stream, count=1)
                    if messages:
                        msg_id, data = messages[0]
                        timestamp = datetime.fromtimestamp(int(msg_id.split('-')[0]) / 1000)
                        print(f'   ⏰ 最新消息时间: {timestamp.strftime(\"%Y-%m-%d %H:%M:%S\")}')
                        
                        # 显示消息内容摘要
                        for key, value in data.items():
                            try:
                                parsed = json.loads(value)
                                if isinstance(parsed, dict):
                                    if 'payload' in parsed:
                                        payload = parsed['payload']
                                        if 'forecasts' in payload:
                                            print(f'   📊 天气预报数据: {len(payload[\"forecasts\"])} 个预报')
                                        elif 'detections' in payload:
                                            print(f'   📸 图片分析: {len(payload[\"detections\"])} 个检测对象')
                                        elif 'assessment' in payload:
                                            risk = payload['assessment'].get('risk_level', 'UNKNOWN')
                                            print(f'   🏥 健康评估: 风险等级 {risk}')
                                        elif 'requested_item' in payload:
                                            item = payload['requested_item']
                                            print(f'   📦 后勤请求: {item}')
                                        elif 'results' in payload:
                                            print(f'   🗺️ 路径分析: {len(payload[\"results\"])} 条路径')
                                        else:
                                            print(f'   📄 数据类型: {list(payload.keys())[:3]}')
                                    else:
                                        print(f'   📄 数据类型: {list(parsed.keys())[:3]}')
                            except:
                                print(f'   📄 原始数据: {str(value)[:50]}...')
            else:
                # 非流数据
                data_type = r.type(stream)
                print(f'\\n🔧 {stream}: {data_type} 类型')
        except Exception as e:
            print(f'\\n❌ 读取 {stream} 时出错: {e}')

except Exception as e:
    print(f'❌ 连接Redis时出错: {e}')
"
    
    log_info "💡 提示: 使用 'docker-compose -f docker-compose.test.yml exec redis-test redis-cli' 可以直接访问Redis"
}

# 主函数
main() {
    local command=${1:-help}
    
    case $command in
        "setup")
            setup_test_environment
            ;;
        "cleanup")
            cleanup_test_environment
            ;;
        "weather")
            test_weather_agent
            ;;
        "health")
            test_health_agent
            ;;
        "photo-analysis")
            test_photo_analysis_agent
            ;;
        "interview")
            test_interview_agent
            ;;
        "logistics")
            test_logistics_agent
            ;;
        "path-analysis")
            test_path_analysis_agent
            ;;
        "redis")
            view_redis_data
            ;;
        "list")
            echo "可用的Agent:"
            for agent in "${AVAILABLE_AGENTS[@]}"; do
                echo "  - $agent"
            done
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

# 运行主函数
main "$@"