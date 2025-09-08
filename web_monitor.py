#!/usr/bin/env python3
"""
SAR System Web Monitor
简单的Web界面用于监控Agent状态和系统数据
"""

import os
import json
import time
from datetime import datetime, timezone
from flask import Flask, render_template_string, jsonify
import redis
from typing import Dict, List, Any

app = Flask(__name__)

# Redis连接
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

# HTML模板
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>SAR System Monitor</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: #2c3e50; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        .card { background: white; padding: 20px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .status { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: bold; }
        .status.running { background: #27ae60; color: white; }
        .status.stopped { background: #e74c3c; color: white; }
        .status.error { background: #e67e22; color: white; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
        .metric { background: #ecf0f1; padding: 10px; border-radius: 4px; margin: 5px 0; }
        .metric-value { font-size: 24px; font-weight: bold; color: #2c3e50; }
        .metric-label { font-size: 14px; color: #7f8c8d; }
        .log-entry { font-family: monospace; font-size: 12px; background: #2c3e50; color: #ecf0f1; padding: 10px; border-radius: 4px; margin: 5px 0; }
        .refresh-btn { background: #3498db; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; }
        .refresh-btn:hover { background: #2980b9; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #f8f9fa; }
        .json-data { background: #f8f9fa; padding: 10px; border-radius: 4px; font-family: monospace; font-size: 12px; white-space: pre-wrap; max-height: 300px; overflow-y: auto; }
    </style>
    <script>
        function refreshData() {
            location.reload();
        }
        
        // 自动刷新
        setInterval(refreshData, 30000); // 每30秒刷新
        
        // 获取实时数据
        async function fetchStreamData(streamName) {
            try {
                const response = await fetch(`/api/stream/${streamName}`);
                const data = await response.json();
                return data;
            } catch (error) {
                console.error('Error fetching stream data:', error);
                return [];
            }
        }
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚁 SAR Multi-Agent System Monitor</h1>
            <p>Last updated: {{ current_time }}</p>
            <button class="refresh-btn" onclick="refreshData()">🔄 Refresh</button>
        </div>
        
        <div class="grid">
            <!-- 系统概览 -->
            <div class="card">
                <h2>📊 System Overview</h2>
                <div class="metric">
                    <div class="metric-value">{{ total_streams }}</div>
                    <div class="metric-label">Active Streams</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{{ total_messages }}</div>
                    <div class="metric-label">Total Messages</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{{ redis_connected | yesno:"✅,❌" }}</div>
                    <div class="metric-label">Redis Connection</div>
                </div>
            </div>
            
            <!-- Agent状态 -->
            <div class="card">
                <h2>🤖 Agent Status</h2>
                <table>
                    <tr><th>Agent</th><th>Status</th><th>Messages</th></tr>
                    {% for agent, info in agents.items() %}
                    <tr>
                        <td>{{ agent }}</td>
                        <td><span class="status {{ info.status }}">{{ info.status }}</span></td>
                        <td>{{ info.message_count }}</td>
                    </tr>
                    {% endfor %}
                </table>
            </div>
        </div>
        
        <!-- 数据流 -->
        <div class="card">
            <h2>📡 Data Streams</h2>
            <table>
                <tr><th>Stream</th><th>Messages</th><th>Last Activity</th><th>Latest Data</th></tr>
                {% for stream, info in streams.items() %}
                <tr>
                    <td>{{ stream }}</td>
                    <td>{{ info.length }}</td>
                    <td>{{ info.last_activity }}</td>
                    <td>
                        {% if info.latest_data %}
                        <details>
                            <summary>View Data</summary>
                            <div class="json-data">{{ info.latest_data }}</div>
                        </details>
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </table>
        </div>
        
        <!-- 最近活动 -->
        <div class="card">
            <h2>📝 Recent Activity</h2>
            {% for entry in recent_activity %}
            <div class="log-entry">
                [{{ entry.timestamp }}] {{ entry.stream }}: {{ entry.message }}
            </div>
            {% endfor %}
        </div>
    </div>
</body>
</html>
"""

def get_redis_info() -> Dict[str, Any]:
    """获取Redis信息"""
    try:
        redis_client.ping()
        redis_connected = True
        
        # 获取所有流
        streams = redis_client.keys("*.raw")
        total_streams = len(streams)
        total_messages = 0
        
        stream_info = {}
        for stream in streams:
            try:
                length = redis_client.xlen(stream)
                total_messages += length
                
                # 获取最新消息
                latest_messages = redis_client.xrevrange(stream, count=1)
                latest_data = None
                last_activity = "N/A"
                
                if latest_messages:
                    msg_id, msg_data = latest_messages[0]
                    last_activity = datetime.fromtimestamp(
                        int(msg_id.split('-')[0]) / 1000
                    ).strftime('%Y-%m-%d %H:%M:%S')
                    
                    # 解析消息数据
                    if 'data' in msg_data:
                        try:
                            latest_data = json.dumps(
                                json.loads(msg_data['data']), 
                                indent=2
                            )
                        except:
                            latest_data = str(msg_data['data'])
                    elif 'body' in msg_data:
                        try:
                            latest_data = json.dumps(
                                json.loads(msg_data['body']), 
                                indent=2
                            )
                        except:
                            latest_data = str(msg_data['body'])
                
                stream_info[stream] = {
                    'length': length,
                    'last_activity': last_activity,
                    'latest_data': latest_data
                }
                
            except Exception as e:
                stream_info[stream] = {
                    'length': 0,
                    'last_activity': 'Error',
                    'latest_data': str(e)
                }
        
        return {
            'redis_connected': redis_connected,
            'total_streams': total_streams,
            'total_messages': total_messages,
            'streams': stream_info
        }
        
    except Exception as e:
        return {
            'redis_connected': False,
            'total_streams': 0,
            'total_messages': 0,
            'streams': {},
            'error': str(e)
        }

def get_agent_info() -> Dict[str, Dict[str, Any]]:
    """获取Agent信息"""
    agents = {
        'weather-agent': {'status': 'unknown', 'message_count': 0},
        'health-agent': {'status': 'unknown', 'message_count': 0},
        'photo-analysis-agent': {'status': 'unknown', 'message_count': 0},
        'logistics-agent': {'status': 'unknown', 'message_count': 0},
        'interview-agent': {'status': 'unknown', 'message_count': 0},
        'path-analysis-agent': {'status': 'unknown', 'message_count': 0}
    }
    
    try:
        # 根据流活动推断Agent状态
        stream_to_agent = {
            'weather.forecast.raw': 'weather-agent',
            'health.assessment.raw': 'health-agent', 
            'photo.analysis.raw': 'photo-analysis-agent',
            'logistics.requests.raw': 'logistics-agent',
            'path.analysis.raw': 'path-analysis-agent'
        }
        
        current_time = time.time()
        
        for stream, agent in stream_to_agent.items():
            try:
                messages = redis_client.xrevrange(stream, count=1)
                if messages:
                    msg_id, _ = messages[0]
                    msg_timestamp = int(msg_id.split('-')[0]) / 1000
                    
                    # 如果最近5分钟内有活动，认为Agent正在运行
                    if current_time - msg_timestamp < 300:  # 5分钟
                        agents[agent]['status'] = 'running'
                    else:
                        agents[agent]['status'] = 'stopped'
                    
                    # 获取消息数量
                    agents[agent]['message_count'] = redis_client.xlen(stream)
                else:
                    agents[agent]['status'] = 'stopped'
                    
            except Exception as e:
                agents[agent]['status'] = 'error'
                agents[agent]['error'] = str(e)
        
        return agents
        
    except Exception as e:
        # 如果出错，返回默认状态
        for agent in agents:
            agents[agent]['status'] = 'error'
            agents[agent]['error'] = str(e)
        return agents

def get_recent_activity(limit: int = 10) -> List[Dict[str, str]]:
    """获取最近活动"""
    activities = []
    
    try:
        streams = redis_client.keys("*.raw")
        all_messages = []
        
        for stream in streams:
            try:
                messages = redis_client.xrevrange(stream, count=5)
                for msg_id, msg_data in messages:
                    timestamp = datetime.fromtimestamp(
                        int(msg_id.split('-')[0]) / 1000
                    ).strftime('%H:%M:%S')
                    
                    # 提取消息摘要
                    message_summary = "New message"
                    if 'data' in msg_data:
                        try:
                            data = json.loads(msg_data['data'])
                            if isinstance(data, dict):
                                if 'agent_name' in data.get('metadata', {}):
                                    message_summary = f"Data from {data['metadata']['agent_name']}"
                                elif 'forecasts' in data:
                                    message_summary = "Weather forecast data"
                                elif 'detections' in data:
                                    message_summary = f"Photo analysis: {len(data['detections'])} detections"
                        except:
                            pass
                    
                    all_messages.append({
                        'timestamp': timestamp,
                        'stream': stream,
                        'message': message_summary,
                        'msg_time': int(msg_id.split('-')[0])
                    })
            except:
                continue
        
        # 按时间排序
        all_messages.sort(key=lambda x: x['msg_time'], reverse=True)
        
        return all_messages[:limit]
        
    except Exception as e:
        return [{'timestamp': 'Error', 'stream': 'system', 'message': str(e)}]

@app.route('/')
def index():
    """主页"""
    redis_info = get_redis_info()
    agent_info = get_agent_info()
    recent_activity = get_recent_activity()
    
    return render_template_string(
        HTML_TEMPLATE,
        current_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        redis_connected=redis_info['redis_connected'],
        total_streams=redis_info['total_streams'],
        total_messages=redis_info['total_messages'],
        streams=redis_info['streams'],
        agents=agent_info,
        recent_activity=recent_activity
    )

@app.route('/api/status')
def api_status():
    """API状态端点"""
    return jsonify({
        'redis': get_redis_info(),
        'agents': get_agent_info(),
        'timestamp': datetime.now(timezone.utc).isoformat()
    })

@app.route('/api/stream/<stream_name>')
def api_stream(stream_name):
    """获取指定流的数据"""
    try:
        messages = redis_client.xrevrange(stream_name, count=10)
        data = []
        
        for msg_id, msg_data in messages:
            timestamp = datetime.fromtimestamp(
                int(msg_id.split('-')[0]) / 1000
            ).isoformat()
            
            data.append({
                'id': msg_id,
                'timestamp': timestamp,
                'data': msg_data
            })
        
        return jsonify(data)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('MONITOR_PORT', 5000))
    host = os.getenv('MONITOR_HOST', '0.0.0.0')
    
    print(f"🌐 SAR System Monitor starting on http://{host}:{port}")
    print(f"📡 Connecting to Redis at {REDIS_URL}")
    
    app.run(host=host, port=port, debug=False)