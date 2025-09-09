#!/usr/bin/env python3
"""
测试状态检查脚本
快速检查测试环境和Agent状态
"""

import redis
import json
import sys
from datetime import datetime
from typing import Dict, List, Any

def check_redis_connection():
    """检查Redis连接"""
    try:
        r = redis.Redis(host='redis-test', port=6379, decode_responses=True)
        r.ping()
        return True, r
    except Exception as e:
        return False, str(e)

def get_stream_info(redis_client) -> Dict[str, Any]:
    """获取所有流的信息"""
    try:
        streams = redis_client.keys('*.raw')
        stream_info = {}
        
        for stream in streams:
            try:
                length = redis_client.xlen(stream)
                if length > 0:
                    messages = redis_client.xrevrange(stream, count=1)
                    if messages:
                        msg_id, _ = messages[0]
                        last_time = datetime.fromtimestamp(int(msg_id.split('-')[0]) / 1000)
                        stream_info[stream] = {
                            'length': length,
                            'last_activity': last_time.strftime('%H:%M:%S'),
                            'status': '🟢 Active' if (datetime.now() - last_time).seconds < 300 else '🟡 Idle'
                        }
                    else:
                        stream_info[stream] = {
                            'length': length,
                            'last_activity': 'N/A',
                            'status': '🔴 No Data'
                        }
                else:
                    stream_info[stream] = {
                        'length': 0,
                        'last_activity': 'Never',
                        'status': '🔴 Empty'
                    }
            except Exception as e:
                stream_info[stream] = {
                    'length': 0,
                    'last_activity': 'Error',
                    'status': f'❌ Error: {str(e)}'
                }
        
        return stream_info
    except Exception as e:
        return {'error': str(e)}

def analyze_agent_data(redis_client, stream_name: str) -> str:
    """分析特定Agent的数据"""
    try:
        if not redis_client.exists(stream_name):
            return "❌ 流不存在"
        
        length = redis_client.xlen(stream_name)
        if length == 0:
            return "📭 无数据"
        
        messages = redis_client.xrevrange(stream_name, count=1)
        if not messages:
            return "📭 无消息"
        
        msg_id, data = messages[0]
        
        # 分析不同类型的数据
        analysis = []
        
        for key, value in data.items():
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    if 'payload' in parsed:
                        payload = parsed['payload']
                        
                        # Weather data
                        if 'forecasts' in payload:
                            forecast_count = len(payload['forecasts'])
                            analysis.append(f"🌤️ {forecast_count} 个天气预报")
                        
                        # Health assessment
                        elif 'assessment' in payload:
                            risk_level = payload['assessment'].get('risk_level', 'UNKNOWN')
                            analysis.append(f"🏥 健康风险: {risk_level}")
                        
                        # Photo analysis
                        elif 'detections' in payload:
                            detection_count = len(payload['detections'])
                            person_count = len([d for d in payload['detections'] if d.get('class') == 'person'])
                            analysis.append(f"📸 检测到 {detection_count} 个对象, {person_count} 个人")
                        
                        # Logistics request
                        elif 'requested_item' in payload:
                            item = payload['requested_item']
                            priority = payload.get('priority', 'Unknown')
                            analysis.append(f"📦 请求 {item} (优先级: {priority})")
                        
                        # Path analysis
                        elif 'results' in payload:
                            path_count = len(payload['results'])
                            analysis.append(f"🗺️ 分析了 {path_count} 条路径")
                        
                        else:
                            analysis.append(f"📄 数据类型: {list(payload.keys())[:2]}")
                    else:
                        analysis.append(f"📄 包含: {list(parsed.keys())[:2]}")
            except:
                analysis.append(f"📄 原始数据: {str(value)[:30]}...")
        
        return " | ".join(analysis) if analysis else "✅ 有数据"
        
    except Exception as e:
        return f"❌ 分析错误: {str(e)}"

def main():
    print("🧪 SAR Agent 测试状态检查")
    print("=" * 50)
    
    # 检查Redis连接
    redis_ok, redis_result = check_redis_connection()
    
    if not redis_ok:
        print(f"❌ Redis连接失败: {redis_result}")
        print("\n💡 请确保测试环境已启动:")
        print("   ./test_single_agent.sh setup")
        sys.exit(1)
    
    print("✅ Redis连接正常")
    redis_client = redis_result
    
    # 获取流信息
    print(f"\n📊 数据流状态:")
    print("-" * 50)
    
    stream_info = get_stream_info(redis_client)
    
    if 'error' in stream_info:
        print(f"❌ 获取流信息失败: {stream_info['error']}")
        return
    
    if not stream_info:
        print("📭 没有找到任何数据流")
        print("\n💡 尝试运行一些Agent测试:")
        print("   ./test_single_agent.sh weather")
        print("   ./test_single_agent.sh health")
        return
    
    # Agent到流的映射
    agent_streams = {
        'Weather Agent': 'weather.forecast.raw',
        'Health Agent': 'health.assessment.raw',
        'Photo Analysis': 'photo.analysis.raw',
        'Logistics Agent': 'logistics.requests.raw',
        'Path Analysis': 'path.analysis.raw',
        'Interview Agent': 'interview.analysis.raw'
    }
    
    # 显示每个Agent的状态
    for agent_name, stream_name in agent_streams.items():
        if stream_name in stream_info:
            info = stream_info[stream_name]
            analysis = analyze_agent_data(redis_client, stream_name)
            print(f"{info['status']} {agent_name:15} | {info['length']:3} 消息 | {info['last_activity']:8} | {analysis}")
        else:
            print(f"⚪ {agent_name:15} | 未运行")
    
    # 显示其他流
    other_streams = [s for s in stream_info.keys() if s not in agent_streams.values()]
    if other_streams:
        print(f"\n📡 其他数据流:")
        for stream in other_streams:
            info = stream_info[stream]
            print(f"{info['status']} {stream:20} | {info['length']:3} 消息 | {info['last_activity']:8}")
    
    # 总结
    total_messages = sum(info['length'] for info in stream_info.values() if isinstance(info.get('length'), int))
    active_streams = len([s for s in stream_info.values() if s.get('status', '').startswith('🟢')])
    
    print(f"\n📈 总结:")
    print(f"   📊 总消息数: {total_messages}")
    print(f"   🟢 活跃流: {active_streams}/{len(stream_info)}")
    
    if active_streams == 0:
        print(f"\n💡 建议:")
        print(f"   1. 测试Weather Agent: ./test_single_agent.sh weather")
        print(f"   2. 测试Health Agent: ./test_single_agent.sh health")
        print(f"   3. 查看详细数据: ./test_single_agent.sh redis")
    
    print(f"\n🔧 有用的命令:")
    print(f"   查看详细数据: ./test_single_agent.sh redis")
    print(f"   进入容器调试: docker-compose -f docker-compose.test.yml exec test-env bash")
    print(f"   查看容器日志: docker-compose -f docker-compose.test.yml logs test-env")

if __name__ == '__main__':
    main()