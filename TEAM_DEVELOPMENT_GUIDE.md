# 👥 SAR系统团队开发指南

## 🎯 推荐的团队分工策略

### 方案A: 统一Docker + 独立开发 (推荐)

**架构师/DevOps负责**:
- 🐳 统一的Docker基础设施
- 📡 Redis消息总线配置  
- 🔧 CI/CD流水线
- 📊 监控和日志系统

**各Agent开发者负责**:
- 💻 各自Agent的业务逻辑
- 🧪 Agent单元测试
- 📝 Agent文档和API规范
- 🔌 与消息总线的集成

### 方案B: 完全独立Docker (适合大团队)

每个Agent开发者维护自己的:
- 🐳 独立的Dockerfile
- 🔧 独立的docker-compose配置
- 🧪 独立的测试环境

## 📋 具体分工建议

### 👨‍💼 项目架构师 (1人)
```bash
负责文件:
├── docker-compose.yml           # 主编排文件
├── docker-compose.prod.yml      # 生产环境配置
├── shared/                      # 共享模块
├── agent_orchestrator.py        # 协调器
└── monitoring/                  # 监控配置
```

### 👨‍🔬 各Agent开发者 (6人)

#### Weather Agent开发者
```bash
agents/weather/
├── main.py
├── Dockerfile.weather           # 独立Dockerfile
├── docker-compose.weather.yml   # 独立测试环境
├── requirements.txt
├── tests/
└── README.md
```

#### Health Agent开发者  
```bash
agents/health/
├── main.py
├── Dockerfile.health
├── docker-compose.health.yml
├── requirements.txt
├── tests/
└── README.md
```

#### 其他Agent类似...

### 🧪 测试工程师 (1人)
```bash
负责:
├── tests/integration/           # 集成测试
├── tests/performance/           # 性能测试
├── docker-compose.test.yml      # 测试环境
└── test_all_agents.sh          # 全系统测试
```

## 🚀 团队开发工作流

### Phase 1: 环境设置 (第1天)

#### 架构师任务:
```bash
# 1. 设置项目基础架构
git clone <project-repo>
cd sar-agent-mvp

# 2. 创建团队开发环境
./team_dev.sh setup-all

# 3. 设置CI/CD流水线 (GitHub Actions/Jenkins)
# 4. 配置监控和日志系统
```

#### 各Agent开发者任务:
```bash
# 1. 克隆项目并设置个人开发环境
git clone <project-repo>
cd sar-agent-mvp

# 2. 设置自己负责的Agent开发环境
./team_dev.sh setup weather  # 替换为自己的Agent

# 3. 配置个人API密钥
cp .env.template agents/weather/.env
# 编辑.env文件
```

### Phase 2: 并行开发 (第2-7天)

#### 每个开发者的日常工作流:

**启动开发环境**:
```bash
cd agents/weather  # 进入自己的Agent目录
./dev.sh start     # 启动独立开发环境
```

**开发调试**:
```bash
# 查看日志
./dev.sh logs

# 进入容器调试
./dev.sh shell

# 测试Agent
./dev.sh test

# 重新构建
./dev.sh build
```

**代码提交**:
```bash
# 在自己的分支上开发
git checkout -b feature/weather-agent-improvements
git add agents/weather/
git commit -m "Improve weather data parsing"
git push origin feature/weather-agent-improvements
```

### Phase 3: 集成测试 (第8-10天)

#### 测试工程师任务:
```bash
# 1. 运行所有Agent的单元测试
./team_dev.sh test weather
./team_dev.sh test health
# ... 其他Agent

# 2. 集成测试
./start_sar_system.sh full
python check_test_status.py

# 3. 性能测试
docker-compose --profile monitoring up -d
# 访问监控界面分析性能
```

#### 架构师任务:
```bash
# 1. 协调各Agent的集成
docker-compose up -d

# 2. 验证Agent间通信
./test_single_agent.sh redis

# 3. 部署到测试环境
docker-compose -f docker-compose.prod.yml up -d
```

## 🔧 开发工具和命令

### 团队开发脚本: `team_dev.sh`

```bash
# 设置所有Agent的开发环境
./team_dev.sh setup-all

# 设置特定Agent的开发环境
./team_dev.sh setup weather

# 启动Agent开发环境
./team_dev.sh dev weather

# 查看所有Agent状态
./team_dev.sh status-all

# 清理所有开发环境
./team_dev.sh clean-all
```

### 各Agent目录下的开发脚本: `dev.sh`

```bash
cd agents/weather

# 启动开发环境
./dev.sh start

# 查看日志
./dev.sh logs

# 进入开发容器
./dev.sh shell

# 测试Agent
./dev.sh test

# 停止环境
./dev.sh stop

# 清理环境
./dev.sh clean
```

## 📊 团队协作最佳实践

### 1. 代码分支策略

```bash
main                    # 主分支，稳定版本
├── develop            # 开发分支，集成最新功能
├── feature/weather-*  # Weather Agent功能分支
├── feature/health-*   # Health Agent功能分支
├── feature/photo-*    # Photo Analysis Agent功能分支
├── hotfix/*          # 紧急修复分支
└── release/*         # 发布分支
```

### 2. Docker端口分配

```bash
Redis端口分配:
- 主系统Redis:     6379
- 测试Redis:       6380
- Weather Dev:     6381
- Health Dev:      6382
- Photo Dev:       6383
- Interview Dev:   6384
- Logistics Dev:   6385
- Path Dev:        6386
```

### 3. 环境变量管理

**全局环境变量** (项目根目录):
```bash
.env                 # 主环境配置
.env.template        # 环境变量模板
.env.prod           # 生产环境配置
```

**Agent专用环境变量**:
```bash
agents/weather/.env      # Weather Agent专用配置
agents/health/.env       # Health Agent专用配置
# ... 其他Agent
```

### 4. 测试策略

**单元测试** (各Agent开发者负责):
```bash
agents/weather/tests/
├── test_weather_api.py
├── test_data_parsing.py
└── test_redis_integration.py
```

**集成测试** (测试工程师负责):
```bash
tests/integration/
├── test_agent_communication.py
├── test_full_workflow.py
└── test_performance.py
```

### 5. 监控和日志

**开发环境监控**:
```bash
# 每个Agent都有独立的日志
docker-compose -f agents/weather/docker-compose.dev.yml logs -f

# 统一监控所有开发环境
./team_dev.sh status-all
```

**生产环境监控**:
```bash
# Web监控界面
docker-compose --profile monitoring up -d web-monitor
# 访问: http://localhost:5000

# 协调器监控
docker-compose --profile orchestrator up -d orchestrator
```

## 🎯 团队角色详细分工

### 👨‍💼 架构师 (DevOps)
**主要职责**:
- 🏗️ 系统架构设计
- 🐳 Docker基础设施
- 📡 消息总线设计
- 🔧 CI/CD流水线
- 📊 监控和告警

**日常工作**:
- 维护主docker-compose.yml
- 审查Agent集成代码
- 管理生产环境部署
- 解决跨Agent的技术问题

### 👨‍🔬 Weather Agent开发者
**主要职责**:
- 🌤️ 天气数据获取和解析
- 📡 与NOAA API集成
- 🔄 数据格式标准化
- 🧪 单元测试和文档

**技术栈**:
- Python requests
- NOAA Weather API
- Redis消息发布
- Docker容器化

### 👩‍⚕️ Health Agent开发者
**主要职责**:
- 🏥 健康风险评估算法
- 🤖 与Gemini AI集成
- 📊 医疗数据分析
- 💊 药物和设备建议

**技术栈**:
- Google Gemini AI
- 医疗知识库
- 风险评估模型
- Redis消息处理

### 📸 Photo Analysis开发者
**主要职责**:
- 👁️ 图像目标检测
- 👤 人员识别和分析
- 🎨 计算机视觉算法
- 🔍 SAR相关特征提取

**技术栈**:
- YOLO模型
- OpenCV
- Face Recognition
- 深度学习框架

### 🎤 Interview Agent开发者
**主要职责**:
- 📄 PDF文档解析
- 🧠 自然语言处理
- 🔍 关键信息提取
- 📊 置信度评估

**技术栈**:
- OpenAI GPT
- PDF处理库
- NLP技术
- 文本分析

### 📦 Logistics Agent开发者
**主要职责**:
- 🚛 资源需求分析
- 📋 供应链管理
- 🎯 优先级排序
- 📊 需求预测

**技术栈**:
- 供应链算法
- 优化算法
- 数据分析
- 决策支持系统

### 🗺️ Path Analysis开发者
**主要职责**:
- 🗺️ 地理信息系统
- 🧭 路径规划算法
- 🏔️ 地形分析
- 📍 最优路径计算

**技术栈**:
- OSM地图数据
- 地理信息处理
- 路径规划算法
- DEM地形数据

### 🧪 测试工程师
**主要职责**:
- ✅ 集成测试设计
- 📈 性能测试
- 🐛 缺陷跟踪
- 📊 测试报告

**技术栈**:
- 自动化测试框架
- 性能测试工具
- 监控和分析
- 测试数据管理

## 💡 协作建议

### 1. 每日站会 (15分钟)
- 各Agent开发者报告进度
- 讨论技术难点和依赖
- 协调集成测试时间

### 2. 周度技术评审
- 代码审查和架构讨论
- Agent接口标准化
- 性能优化建议

### 3. 沟通渠道
- Slack/Teams: 日常沟通
- GitHub Issues: 缺陷跟踪
- Confluence/Notion: 技术文档
- 代码评审: Pull Request

### 4. 发布流程
```bash
# 1. 功能开发完成
git checkout develop
git merge feature/weather-improvements

# 2. 集成测试
./start_sar_system.sh full
python check_test_status.py

# 3. 创建发布分支
git checkout -b release/v1.1.0

# 4. 生产部署
docker-compose -f docker-compose.prod.yml up -d

# 5. 发布标签
git tag v1.1.0
git push origin v1.1.0
```

这种分工方式的优势:
- ✅ **专业化**: 每人专注自己擅长的领域
- ✅ **并行开发**: 减少相互依赖和冲突
- ✅ **独立测试**: 每个Agent可以独立开发和测试
- ✅ **统一集成**: 通过标准化接口集成
- ✅ **灵活部署**: 支持独立部署和整体部署
