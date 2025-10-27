# Command Agent - SAR System Commander 🎯

## 概述

Command Agent 是整个 SAR 系统的智能指挥中心，使用 **AutoGen** 来协调所有 specialist agents，为用户提供对话式的搜索救援决策支持。

## 🎯 核心功能

### 1. 智能编排 (Orchestration)
- 理解用户自然语言需求
- 自动识别需要的 specialist agents
- 协调多个 agents 协作
- 聚合分析结果

### 2. 对话式交互
- 自然语言问答
- 上下文管理
- 持续深度分析
- 个性化建议

### 3. 实时数据集成
- 从 Redis Streams 读取最新数据
- 整合所有 agents 的分析结果
- 动态更新建议

## 🏗️ 架构

```
User Input
    ↓
Command Agent (AutoGen GroupChat)
    ↓
┌─────────────────────────────────────┐
│  Specialist Agents (AutoGen Agents) │
│  - Weather Specialist               │
│  - History Specialist               │
│  - Photo Specialist                 │
│  - Path Planning Specialist         │
│  - Health Assessment Specialist     │
│  - Commander (协调者)               │
└─────────────────────────────────────┘
    ↓
Redis Integration
    ↓
Final Report to User
```

## 🚀 使用方式

### 本地运行

```bash
# 安装依赖
pip install -r agents/command_agent/requirements.txt

# 设置环境变量
export OPENAI_API_KEY="your-key"
export REDIS_URL="redis://localhost:6379"

# 运行
python agents/command_agent/main.py
```

### Docker 运行

```bash
# 构建镜像
docker-compose build command-agent

# 运行
docker-compose up command-agent
```

## 💬 对话示例

```
👤 User: "我要搜索一个65岁的老人，他有老年痴呆，失踪2天了"

🤖 Command Agent: 
   "我理解。让我协调各个部门收集信息..."
   
   [Weather Specialist: 查看未来48小时天气]
   "天气情况: 明天晴天，温度25°C"
   
   [History Specialist: 查询相似案例]
   "找到了3个相似案例，主要都是在水源附近找到"
   
   [Health Specialist: 评估健康风险]
   "老年人痴呆需要尽快找到，高风险"
   
🤖 Command Agent:
   "基于分析，我建议:
   1. 优先搜索水源附近1公里范围
   2. 使用无人机在开阔地搜索
   3. 需要医疗团队随时待命
   
   需要我详细安排搜索路线吗？"

👤 User: "给我规划路线"

🤖 Command Agent:
   [Path Planning Agent 开始工作]
   "收到，正在规划3条搜索路线..."
```

## 🔧 配置

### 环境变量

- `OPENAI_API_KEY`: OpenAI API key (必需)
- `REDIS_URL`: Redis 连接 URL (默认: redis://localhost:6379)

### LLM 配置

在 `main.py` 中修改 `llm_config`:

```python
llm_config = {
    "model": "gpt-4",        # 或 "gpt-3.5-turbo"
    "api_key": OPENAI_API_KEY,
    "temperature": 0.7,
    "timeout": 120
}
```

## 📊 Specialist Agents

| Agent | 职责 | 数据源 |
|-------|------|--------|
| Weather Specialist | 天气分析 | weather.forecast.raw |
| History Specialist | 历史案例 | history.out.raw |
| Photo Specialist | 照片分析 | photo.analysis.raw |
| Path Planning Specialist | 路线规划 | path.analysis.raw |
| Health Assessment Specialist | 健康评估 | health.assessment.raw |
| Commander | 协调总结 | 所有 streams |

## 🔄 工作流程

1. **用户输入** → Command Agent 接收
2. **意图理解** → LLM 分析需求
3. **任务分解** → 识别需要的 specialists
4. **协调执行** → AutoGen 管理对话
5. **数据获取** → 从 Redis 读取
6. **结果聚合** → Commander 综合报告
7. **返回用户** → 展示最终建议

## 🎯 下一步

- [ ] 完善 chat 方法实现
- [ ] 添加 entry point agent
- [ ] 实现历史管理
- [ ] 添加错误处理
- [ ] 优化响应速度

## 📝 License

MIT

