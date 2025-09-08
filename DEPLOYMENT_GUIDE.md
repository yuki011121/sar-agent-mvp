# SAR Multi-Agent System 本地部署指南

## 🚀 快速开始

### 1. 环境准备

#### 系统要求
- Docker & Docker Compose
- Python 3.10+ (可选，用于本地开发)
- 至少8GB RAM
- 10GB可用磁盘空间

#### API密钥准备
你需要获取以下API密钥：

**必需的API密钥 (至少选择一个):**
- **OpenAI API Key**: 用于Interview Agent和History Agent
  - 获取地址: https://platform.openai.com/api-keys
- **Google Gemini API Key**: 用于Health Agent, Path Analysis, Logistics Agents
  - 获取地址: https://aistudio.google.com/app/apikey

### 2. 配置环境变量

```bash
# 复制环境变量模板
cp .env.template .env

# 编辑 .env 文件，填入你的API密钥
nano .env
```

**最小配置示例:**
```bash
# 如果你只有OpenAI API Key
OPENAI_API_KEY=sk-your-openai-key-here
LLM_PROVIDER=openai

# 如果你只有Gemini API Key  
GEMINI_API_KEY=your-gemini-key-here
GOOGLE_API_KEY=your-gemini-key-here
API_KEY=your-gemini-key-here
LLM_PROVIDER=google
```

### 3. 构建和启动系统

```bash
# 构建Docker镜像
docker-compose build

# 启动基础设施 (Redis + MinIO)
docker-compose up -d redis minio

# 等待服务就绪 (约30秒)
docker-compose logs redis minio

# 启动所有Agent
docker-compose up -d
```

## 📊 系统架构

### Agent通信架构
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Weather       │    │   Health        │    │   Photo         │
│   Agent         │    │   Agent         │    │   Analysis      │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          │              ┌───────▼───────┐              │
          └──────────────►│     Redis     │◄─────────────┘
                         │   Message     │
          ┌──────────────►│     Bus       │◄─────────────┐
          │              └───────▲───────┘              │
          │                      │                      │
┌─────────┴───────┐    ┌─────────┴───────┐    ┌─────────┴───────┐
│   Interview     │    │   Logistics     │    │   Path          │
│   Agent         │    │   Agent         │    │   Analysis      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### 数据流
1. **Weather Agent** → 定期获取天气数据 → Redis Stream
2. **Photo Analysis Agent** → 监控图片文件夹 → 分析图片 → Redis Stream  
3. **Health Agent** → 读取任务和天气数据 → 健康风险评估 → Redis Stream
4. **Logistics Agent** → 模拟资源请求 → Redis Stream
5. **Interview Agent** → 分析访谈记录 → 一次性运行
6. **Path Analysis Agent** → 路径规划分析 → 一次性运行

## 🔧 运行模式

### 模式1: 完整系统运行
```bash
# 启动所有服务
docker-compose up -d

# 查看所有服务状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

### 模式2: 选择性运行Agent
```bash
# 只运行持续性Agent
docker-compose up -d redis minio weather-agent health-agent photo-analysis-agent logistics-agent

# 手动运行一次性Agent
docker-compose run --rm interview-agent
docker-compose run --rm path-analysis-agent
```

### 模式3: 开发模式
```bash
# 启动基础设施和开发容器
docker-compose up -d redis minio dev

# 进入开发容器
docker-compose exec dev bash

# 在容器内手动运行Agent
python agents/weather/main.py
python agents/health/main.py
```

## 📁 目录结构和数据管理

### 重要目录
- `input_images/`: 放置待分析的图片
- `data/transcripts/`: 放置访谈记录PDF
- `agents/path_analysis/data/`: DEM地形数据
- `shared/`: Agent间通信模块

### 数据持久化
- Redis数据: `redis_data` volume
- MinIO数据: `minio_data` volume  
- YOLO模型: `yolo_models` volume

## 🖥️ 管理界面

### Redis管理界面 (可选)
```bash
# 启动Redis管理界面
docker-compose --profile tools up -d redis-commander

# 访问: http://localhost:8081
```

### 系统监控 (可选)
```bash  
# 启动监控服务
docker-compose --profile monitoring up -d agent-monitor

# 查看监控日志
docker-compose logs -f agent-monitor
```

### MinIO管理界面
- 访问: http://localhost:9001
- 用户名: minioadmin
- 密码: minioadmin

## 🧪 测试系统

### 1. 测试Photo Analysis Agent
```bash
# 复制测试图片到input_images目录
cp input_images/basketball.png input_images/test.png

# 查看分析结果
docker-compose logs photo-analysis-agent
```

### 2. 测试Weather Agent
```bash
# 查看天气数据获取
docker-compose logs weather-agent

# 在Redis中查看数据
docker-compose exec redis redis-cli
> XRANGE weather.forecast.raw - +
```

### 3. 测试Health Agent
```bash
# 查看健康评估
docker-compose logs health-agent

# 查看评估结果
docker-compose exec redis redis-cli
> XRANGE health.assessment.raw - +
```

## 🔍 故障排除

### 常见问题

#### 1. Agent无法连接Redis
```bash
# 检查Redis状态
docker-compose ps redis
docker-compose logs redis

# 重启Redis
docker-compose restart redis
```

#### 2. API密钥错误
```bash
# 检查环境变量
docker-compose config

# 查看Agent日志
docker-compose logs <agent-name>
```

#### 3. 内存不足
```bash
# 查看资源使用
docker stats

# 停止部分Agent
docker-compose stop photo-analysis-agent path-analysis-agent
```

#### 4. YOLO模型下载失败
```bash
# 手动下载模型
docker-compose exec dev python -c "
from ultralytics import YOLO
model = YOLO('yolov8m.pt')
"
```

### 日志查看
```bash
# 查看所有日志
docker-compose logs

# 查看特定Agent日志
docker-compose logs -f weather-agent

# 查看最近100行日志
docker-compose logs --tail=100 health-agent
```

## 🚀 生产部署建议

### 1. 安全配置
- 更改MinIO默认密码
- 使用Docker Secrets管理API密钥
- 配置防火墙规则

### 2. 性能优化
- 增加Redis内存限制
- 配置Agent并发数
- 使用SSD存储

### 3. 监控告警
- 集成Prometheus + Grafana
- 配置健康检查
- 设置日志轮转

### 4. 备份策略
- 定期备份Redis数据
- 备份配置文件
- 导出重要分析结果

## 📚 API参考

### Redis Streams
- `weather.forecast.raw`: 天气预报数据
- `health.assessment.raw`: 健康风险评估  
- `photo.analysis.raw`: 图片分析结果
- `logistics.requests.raw`: 后勤资源请求
- `mission.new`: 任务信息
- `field.observation.raw`: 现场观察数据

### 环境变量完整列表
参见 `.env.template` 文件中的详细说明。

## 🤝 贡献指南

1. Fork项目
2. 创建特性分支
3. 提交更改
4. 推送到分支
5. 创建Pull Request

## 📄 许可证

本项目基于MIT许可证开源。详见LICENSE文件。