#!/usr/bin/env python3
"""
SAR Multi-Agent System Orchestrator
统一管理和协调所有Agent的运行
"""

import os
import time
import json
import logging
import threading
import signal
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import redis
import subprocess

from shared.redis_bus import RedisBus
from shared.a2a_envelope import wrap_envelope, parse_message_from_stream

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('SAR-Orchestrator')

class AgentStatus(Enum):
    STOPPED = "stopped"
    STARTING = "starting" 
    RUNNING = "running"
    ERROR = "error"
    COMPLETED = "completed"

@dataclass
class AgentConfig:
    name: str
    module_path: str
    agent_type: str  # "continuous", "on_demand", "scheduled"
    dependencies: List[str]
    restart_policy: str  # "always", "on_failure", "never"
    health_check_interval: int = 30
    max_restarts: int = 3
    environment: Dict[str, str] = None
    
class SAROrchestratorError(Exception):
    """Orchestrator相关异常"""
    pass

class AgentManager:
    """单个Agent的管理器"""
    
    def __init__(self, config: AgentConfig, redis_bus: RedisBus):
        self.config = config
        self.bus = redis_bus
        self.status = AgentStatus.STOPPED
        self.process: Optional[subprocess.Popen] = None
        self.restart_count = 0
        self.last_heartbeat = None
        self.start_time = None
        self.error_message = None
        
    def start(self) -> bool:
        """启动Agent"""
        try:
            if self.status == AgentStatus.RUNNING:
                logger.warning(f"Agent {self.config.name} is already running")
                return True
                
            logger.info(f"Starting agent: {self.config.name}")
            self.status = AgentStatus.STARTING
            
            # 设置环境变量
            env = os.environ.copy()
            if self.config.environment:
                env.update(self.config.environment)
            
            # 启动进程
            self.process = subprocess.Popen(
                [sys.executable, self.config.module_path],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.start_time = datetime.now(timezone.utc)
            self.status = AgentStatus.RUNNING
            self.error_message = None
            
            logger.info(f"Agent {self.config.name} started with PID {self.process.pid}")
            return True
            
        except Exception as e:
            self.status = AgentStatus.ERROR
            self.error_message = str(e)
            logger.error(f"Failed to start agent {self.config.name}: {e}")
            return False
    
    def stop(self) -> bool:
        """停止Agent"""
        try:
            if self.status == AgentStatus.STOPPED:
                return True
                
            logger.info(f"Stopping agent: {self.config.name}")
            
            if self.process and self.process.poll() is None:
                self.process.terminate()
                
                # 等待优雅关闭
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    logger.warning(f"Force killing agent {self.config.name}")
                    self.process.kill()
                    self.process.wait()
            
            self.status = AgentStatus.STOPPED
            self.process = None
            logger.info(f"Agent {self.config.name} stopped")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop agent {self.config.name}: {e}")
            return False
    
    def check_health(self) -> bool:
        """检查Agent健康状态"""
        try:
            if self.status != AgentStatus.RUNNING:
                return False
                
            if not self.process:
                return False
                
            # 检查进程是否还在运行
            if self.process.poll() is not None:
                # 进程已退出
                return_code = self.process.returncode
                stdout, stderr = self.process.communicate()
                
                if return_code == 0:
                    self.status = AgentStatus.COMPLETED
                    logger.info(f"Agent {self.config.name} completed successfully")
                else:
                    self.status = AgentStatus.ERROR
                    self.error_message = f"Process exited with code {return_code}: {stderr}"
                    logger.error(f"Agent {self.config.name} failed: {self.error_message}")
                
                return False
            
            # 检查心跳 (通过Redis流检查活动)
            return self._check_heartbeat()
            
        except Exception as e:
            logger.error(f"Health check failed for agent {self.config.name}: {e}")
            return False
    
    def _check_heartbeat(self) -> bool:
        """检查Agent心跳"""
        try:
            # 查找Agent相关的Redis流
            streams = self.bus.client.keys(f"*{self.config.name.replace('-', '.')}*")
            if not streams:
                return True  # 没有流也认为是健康的
            
            # 检查最近是否有活动
            current_time = time.time()
            for stream in streams:
                try:
                    messages = self.bus.client.xrevrange(stream, count=1)
                    if messages:
                        msg_id, _ = messages[0]
                        # Redis stream ID格式: timestamp-sequence
                        msg_timestamp = int(msg_id.decode().split('-')[0]) / 1000
                        
                        if current_time - msg_timestamp < self.config.health_check_interval * 2:
                            self.last_heartbeat = datetime.now(timezone.utc)
                            return True
                except:
                    continue
            
            # 如果没有最近活动，但进程还在运行，也认为是健康的
            return True
            
        except Exception as e:
            logger.warning(f"Heartbeat check failed for {self.config.name}: {e}")
            return True  # 默认认为健康
    
    def should_restart(self) -> bool:
        """判断是否应该重启"""
        if self.config.restart_policy == "never":
            return False
        
        if self.restart_count >= self.config.max_restarts:
            logger.error(f"Agent {self.config.name} exceeded max restarts ({self.config.max_restarts})")
            return False
        
        if self.config.restart_policy == "always":
            return True
        
        if self.config.restart_policy == "on_failure" and self.status == AgentStatus.ERROR:
            return True
        
        return False
    
    def restart(self) -> bool:
        """重启Agent"""
        if not self.should_restart():
            return False
        
        logger.info(f"Restarting agent {self.config.name} (attempt {self.restart_count + 1})")
        
        self.stop()
        time.sleep(5)  # 等待5秒再重启
        
        if self.start():
            self.restart_count += 1
            return True
        
        return False

class SAROrchestrator:
    """SAR系统协调器"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.bus = RedisBus(redis_url)
        self.agents: Dict[str, AgentManager] = {}
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.mission_active = False
        
        # 注册信号处理器
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # 初始化Agent配置
        self._initialize_agents()
    
    def _signal_handler(self, signum, frame):
        """信号处理器"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.shutdown()
        sys.exit(0)
    
    def _initialize_agents(self):
        """初始化Agent配置"""
        
        # 持续运行的Agent
        continuous_agents = [
            AgentConfig(
                name="weather-agent",
                module_path="agents/weather/main.py",
                agent_type="continuous",
                dependencies=["redis"],
                restart_policy="always",
                health_check_interval=60
            ),
            AgentConfig(
                name="health-agent", 
                module_path="agents/health/main.py",
                agent_type="continuous",
                dependencies=["redis"],
                restart_policy="always",
                health_check_interval=60
            ),
            AgentConfig(
                name="photo-analysis-agent",
                module_path="agents/photo_analysis/main.py", 
                agent_type="continuous",
                dependencies=["redis"],
                restart_policy="always",
                health_check_interval=30
            ),
            AgentConfig(
                name="logistics-agent",
                module_path="agents/logistics/main.py",
                agent_type="continuous", 
                dependencies=["redis"],
                restart_policy="always",
                health_check_interval=60
            )
        ]
        
        # 按需运行的Agent
        on_demand_agents = [
            AgentConfig(
                name="interview-agent",
                module_path="agents/interview/main.py",
                agent_type="on_demand",
                dependencies=["redis"],
                restart_policy="never"
            ),
            AgentConfig(
                name="path-analysis-agent", 
                module_path="agents/path_analysis/main.py",
                agent_type="on_demand",
                dependencies=["redis"],
                restart_policy="never"
            )
        ]
        
        # 创建Agent管理器
        for config in continuous_agents + on_demand_agents:
            self.agents[config.name] = AgentManager(config, self.bus)
    
    def start_continuous_agents(self):
        """启动持续运行的Agent"""
        logger.info("Starting continuous agents...")
        
        for name, agent in self.agents.items():
            if agent.config.agent_type == "continuous":
                if not agent.start():
                    logger.error(f"Failed to start continuous agent: {name}")
                else:
                    logger.info(f"Started continuous agent: {name}")
    
    def start_on_demand_agent(self, agent_name: str) -> bool:
        """启动按需Agent"""
        if agent_name not in self.agents:
            logger.error(f"Unknown agent: {agent_name}")
            return False
        
        agent = self.agents[agent_name]
        if agent.config.agent_type != "on_demand":
            logger.warning(f"Agent {agent_name} is not an on-demand agent")
            return False
        
        return agent.start()
    
    def stop_agent(self, agent_name: str) -> bool:
        """停止指定Agent"""
        if agent_name not in self.agents:
            logger.error(f"Unknown agent: {agent_name}")
            return False
        
        return self.agents[agent_name].stop()
    
    def get_agent_status(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """获取Agent状态"""
        if agent_name not in self.agents:
            return None
        
        agent = self.agents[agent_name]
        return {
            "name": agent.config.name,
            "status": agent.status.value,
            "type": agent.config.agent_type,
            "restart_count": agent.restart_count,
            "start_time": agent.start_time.isoformat() if agent.start_time else None,
            "last_heartbeat": agent.last_heartbeat.isoformat() if agent.last_heartbeat else None,
            "error_message": agent.error_message,
            "pid": agent.process.pid if agent.process else None
        }
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统整体状态"""
        agent_statuses = {}
        for name, agent in self.agents.items():
            agent_statuses[name] = self.get_agent_status(name)
        
        return {
            "orchestrator_running": self.running,
            "mission_active": self.mission_active,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agents": agent_statuses,
            "redis_connected": self._check_redis_connection()
        }
    
    def _check_redis_connection(self) -> bool:
        """检查Redis连接"""
        try:
            self.bus.client.ping()
            return True
        except:
            return False
    
    def _monitor_agents(self):
        """监控Agent健康状态"""
        logger.info("Agent monitoring started")
        
        while self.running:
            try:
                for name, agent in self.agents.items():
                    if agent.config.agent_type == "continuous":
                        if not agent.check_health():
                            logger.warning(f"Agent {name} health check failed")
                            
                            if agent.should_restart():
                                logger.info(f"Attempting to restart agent {name}")
                                agent.restart()
                
                # 发布系统状态到Redis
                self._publish_system_status()
                
                time.sleep(30)  # 每30秒检查一次
                
            except Exception as e:
                logger.error(f"Error in agent monitoring: {e}")
                time.sleep(10)
        
        logger.info("Agent monitoring stopped")
    
    def _publish_system_status(self):
        """发布系统状态到Redis"""
        try:
            status = self.get_system_status()
            message = wrap_envelope(
                payload=status,
                source_name="sar-orchestrator",
                source_version="1.0",
                target_stream="system.status.raw"
            )
            self.bus.publish(message)
        except Exception as e:
            logger.error(f"Failed to publish system status: {e}")
    
    def start_mission(self, mission_data: Dict[str, Any]):
        """启动SAR任务"""
        logger.info("Starting SAR mission")
        self.mission_active = True
        
        # 发布任务信息
        try:
            message = wrap_envelope(
                payload=mission_data,
                source_name="sar-orchestrator", 
                source_version="1.0",
                target_stream="mission.new"
            )
            self.bus.publish(message)
            logger.info("Mission data published to Redis")
        except Exception as e:
            logger.error(f"Failed to publish mission data: {e}")
        
        # 启动持续Agent
        self.start_continuous_agents()
        
        # 根据任务类型启动按需Agent
        if mission_data.get("requires_interview_analysis"):
            self.start_on_demand_agent("interview-agent")
        
        if mission_data.get("requires_path_analysis"):
            self.start_on_demand_agent("path-analysis-agent")
    
    def stop_mission(self):
        """停止SAR任务"""
        logger.info("Stopping SAR mission")
        self.mission_active = False
        
        # 停止按需Agent
        for name, agent in self.agents.items():
            if agent.config.agent_type == "on_demand":
                agent.stop()
    
    def start(self):
        """启动协调器"""
        logger.info("Starting SAR Orchestrator")
        self.running = True
        
        # 启动监控线程
        self.monitor_thread = threading.Thread(target=self._monitor_agents)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        
        logger.info("SAR Orchestrator started")
    
    def shutdown(self):
        """关闭协调器"""
        logger.info("Shutting down SAR Orchestrator")
        self.running = False
        
        # 停止所有Agent
        for name, agent in self.agents.items():
            logger.info(f"Stopping agent: {name}")
            agent.stop()
        
        # 等待监控线程结束
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=10)
        
        logger.info("SAR Orchestrator shutdown complete")

def main():
    """主函数"""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    
    # 创建协调器
    orchestrator = SAROrchestrator(redis_url)
    
    # 启动协调器
    orchestrator.start()
    
    # 示例：启动一个SAR任务
    mission_data = {
        "mission_id": "SAR-2024-001",
        "missing_person": {
            "name": "John Doe",
            "age": 45,
            "last_seen": "Mountain trail near summit",
            "clothing": "Blue jacket, hiking boots"
        },
        "search_area": {
            "center_lat": 35.2828,
            "center_lon": -120.6596,
            "radius_km": 5
        },
        "requires_interview_analysis": True,
        "requires_path_analysis": True,
        "priority": "HIGH",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    orchestrator.start_mission(mission_data)
    
    try:
        # 主循环
        while True:
            time.sleep(60)
            status = orchestrator.get_system_status()
            logger.info(f"System status: {len([a for a in status['agents'].values() if a['status'] == 'running'])} agents running")
    
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    
    finally:
        orchestrator.shutdown()

if __name__ == "__main__":
    main()