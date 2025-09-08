# 🚁 SAR Multi-Agent System

一个基于多智能体架构的搜索救援(Search and Rescue)系统，使用Docker容器化部署，支持多种AI模型和实时数据处理。

## 🎯 系统概览

### 核心Agent
- **Weather Agent**: 获取实时天气数据 (NOAA API)
- **Health Agent**: 健康风险评估 (Gemini AI)
- **Photo Analysis Agent**: 图像分析和人员检测 (YOLO + 计算机视觉)
- **Interview Agent**: 访谈记录分析 (OpenAI GPT)
- **Logistics Agent**: 资源需求管理 (Gemini AI)
- **Path Analysis Agent**: 路径规划分析 (OSM + Gemini AI)

### 架构特点
- 🐳 **Docker容器化**: 每个Agent独立运行
- 📡 **Redis消息总线**: Agent间异步通信
- 🎛️ **统一协调器**: 集中管理和监控
- 🌐 **Web监控界面**: 实时状态监控
- 🔧 **灵活配置**: 支持多种运行模式

## 🚀 快速开始

### 1. 环境准备
```bash
# 克隆项目
git clone <your-repo-url>
cd sar-agent-mvp

# 确保安装Docker和Docker Compose
docker --version
docker-compose --version
```

### 2. 配置API密钥
```bash
# 复制环境变量模板
cp .env.template .env

# 编辑配置文件
nano .env
```

**必需配置 (至少选择一个):**
- `OPENAI_API_KEY`: OpenAI GPT API密钥
- `GEMINI_API_KEY`: Google Gemini API密钥

### 3. 一键启动
```bash
# 使用启动脚本 (推荐)
./start_sar_system.sh full

# 或手动启动
docker-compose build
docker-compose up -d
```

## 📊 监控和管理

### Web监控界面
启动监控服务后访问:
```bash
# 启动Web监控
docker-compose --profile monitoring up -d web-monitor

# 访问监控界面
open http://localhost:5000
```

### Redis管理界面
```bash
# 启动Redis管理工具
docker-compose --profile tools up -d redis-commander

# 访问Redis管理界面
open http://localhost:8081
```

### MinIO存储管理
```bash
# 访问MinIO管理界面
open http://localhost:9001
# 用户名: minioadmin, 密码: minioadmin
```

## 🔧 运行模式

### 完整模式
```bash
./start_sar_system.sh full
# 启动所有Agent和服务
```

### 最小模式
```bash
./start_sar_system.sh minimal
# 只启动核心Agent (天气、健康)
```

### 开发模式
```bash
./start_sar_system.sh dev
# 启动开发环境，可手动运行Agent
```

### 监控模式
```bash
# 启动所有监控服务
docker-compose --profile monitoring up -d

# 启动Agent协调器
docker-compose --profile orchestrator up -d
```

## 🧪 测试系统

### 1. 测试图像分析
```bash
# 添加测试图片
cp input_images/basketball.png input_images/test.png

# 查看分析结果
docker-compose logs photo-analysis-agent
```

### 2. 检查数据流
```bash
# 进入Redis查看数据
docker-compose exec redis redis-cli

# 查看天气数据流
XRANGE weather.forecast.raw - +

# 查看图片分析流
XRANGE photo.analysis.raw - +
```

### 3. 手动运行Agent
```bash
# 进入开发容器
docker-compose exec dev bash

# 运行单个Agent
python agents/weather/main.py
python agents/health/main.py
```

## 📁 项目结构

```
sar-agent-mvp/
├── agents/                    # Agent实现
│   ├── weather/              # 天气Agent
│   ├── health/               # 健康Agent
│   ├── photo_analysis/       # 图像分析Agent
│   ├── interview/            # 访谈分析Agent
│   ├── logistics/            # 后勤Agent
│   └── path_analysis/        # 路径分析Agent
├── shared/                   # 共享模块
│   ├── redis_bus.py         # Redis消息总线
│   ├── a2a_envelope.py      # Agent间消息格式
│   └── mcp_tools.py         # MCP工具
├── input_images/            # 待分析图片
├── data/                    # 数据文件
├── docker-compose.yml       # Docker编排配置
├── agent_orchestrator.py    # Agent协调器
├── web_monitor.py          # Web监控界面
├── start_sar_system.sh     # 启动脚本
├── .env.template           # 环境变量模板
└── DEPLOYMENT_GUIDE.md    # 详细部署指南
```

## 🔌 API参考

### Redis数据流
- `weather.forecast.raw`: 天气预报数据
- `health.assessment.raw`: 健康风险评估
- `photo.analysis.raw`: 图像分析结果
- `logistics.requests.raw`: 后勤资源请求
- `mission.new`: 任务信息
- `field.observation.raw`: 现场观察数据

### 环境变量
参见 `.env.template` 文件获取完整配置选项。

## 🛠️ 故障排除

### 常见问题

1. **Redis连接失败**
   ```bash
   docker-compose restart redis
   docker-compose logs redis
   ```

2. **API密钥错误**
   ```bash
   # 检查环境变量
   docker-compose config
   ```

3. **Agent无法启动**
   ```bash
   # 查看Agent日志
   docker-compose logs <agent-name>
   ```

4. **内存不足**
   ```bash
   # 查看资源使用
   docker stats
   
   # 停止部分Agent
   docker-compose stop photo-analysis-agent
   ```

### 获取帮助
```bash
# 查看启动脚本帮助
./start_sar_system.sh help

# 查看系统状态
./start_sar_system.sh status

# 查看详细部署指南
cat DEPLOYMENT_GUIDE.md
```

## 🔄 系统更新

```bash
# 停止系统
docker-compose down

# 拉取最新代码
git pull

# 重新构建
docker-compose build --no-cache

# 重新启动
./start_sar_system.sh full
```

## 📈 性能优化

### 生产环境建议
- 使用SSD存储
- 增加Redis内存限制
- 配置Agent并发数
- 设置日志轮转
- 配置监控告警

### 资源要求
- **最小**: 4GB RAM, 5GB 磁盘
- **推荐**: 8GB RAM, 10GB 磁盘
- **生产**: 16GB RAM, 50GB 磁盘

## 🤝 贡献指南

1. Fork项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送分支 (`git push origin feature/AmazingFeature`)
5. 创建Pull Request

## 📄 许可证

本项目基于MIT许可证开源。详见 [LICENSE](LICENSE) 文件。

## 🙋 支持

如有问题或建议，请:
1. 查看 [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) 获取详细说明
2. 在GitHub上提交Issue
3. 查看项目Wiki获取更多信息

---

**注意**: 本系统仅用于演示和学习目的。在生产环境中使用前，请确保进行充分的测试和安全评估。