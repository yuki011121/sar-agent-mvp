# 🧪 SAR Agent 单独测试指南

本指南将帮你逐个测试每个Agent，验证其功能，然后再整合整个系统。

## 🚀 快速开始

### 1. 首次设置

```bash
# 1. 配置环境变量
cp .env.template .env
nano .env  # 填入你的API密钥

# 2. 设置测试环境
./test_single_agent.sh setup
```

### 2. 测试单个Agent

```bash
# 查看可用Agent
./test_single_agent.sh list

# 测试特定Agent
./test_single_agent.sh weather
./test_single_agent.sh health
./test_single_agent.sh photo-analysis
```

### 3. 查看结果

```bash
# 查看Redis中的数据
./test_single_agent.sh redis

# 进入测试容器手动调试
docker-compose -f docker-compose.test.yml exec test-env bash
```

## 📋 Agent测试清单

### ✅ 推荐测试顺序

1. **Weather Agent** (最简单，无需API密钥)
2. **Logistics Agent** (简单模拟数据)
3. **Health Agent** (需要Gemini API)
4. **Photo Analysis Agent** (需要图片文件)
5. **Interview Agent** (需要OpenAI API)
6. **Path Analysis Agent** (最复杂，需要地形数据)

---

## 🌤️ 1. Weather Agent 测试

**功能**: 从NOAA获取天气数据并发布到Redis

**前置条件**: 无 (使用公共API)

```bash
# 测试Weather Agent
./test_single_agent.sh weather
```

**预期结果**:
- Redis中出现 `weather.forecast.raw` 流
- 包含天气预报数据 (温度、风速、降水概率等)

**故障排除**:
```bash
# 如果网络问题，检查连接
curl "https://api.weather.gov/points/35.2828,-120.6596"

# 查看详细日志
docker-compose -f docker-compose.test.yml logs test-env
```

---

## 🏥 2. Health Agent 测试

**功能**: 分析健康风险并生成医疗建议

**前置条件**: 需要 `GEMINI_API_KEY` 或 `GOOGLE_API_KEY`

```bash
# 测试Health Agent
./test_single_agent.sh health
```

**预期结果**:
- Redis中出现 `health.assessment.raw` 流
- 包含风险等级、健康风险、推荐行动等

**手动测试**:
```bash
# 进入容器手动运行
docker-compose -f docker-compose.test.yml exec test-env bash

# 在容器内运行
python agents/health/main.py
```

---

## 📸 3. Photo Analysis Agent 测试

**功能**: 分析图片中的人员和物体

**前置条件**: 需要图片文件在 `input_images/` 目录

```bash
# 确保有测试图片
ls input_images/

# 如果没有图片，复制一个测试图片
cp input_images/basketball.png input_images/test.png

# 测试Photo Analysis Agent
./test_single_agent.sh photo-analysis
```

**预期结果**:
- Redis中出现 `photo.analysis.raw` 流
- 包含检测到的对象、人员分析、SAR相关元数据

**手动测试不同图片**:
```bash
# 进入容器
docker-compose -f docker-compose.test.yml exec test-env bash

# 添加新图片到input_images/然后运行
python agents/photo_analysis/main.py
```

---

## 🎤 4. Interview Agent 测试

**功能**: 分析访谈记录PDF文件

**前置条件**: 
- 需要 `OPENAI_API_KEY`
- PDF文件在 `data/transcripts/` 目录

```bash
# 检查是否有PDF文件
ls data/transcripts/

# 测试Interview Agent
./test_single_agent.sh interview
```

**如果没有PDF文件**:
```bash
# Agent会测试基本功能 (置信度评估、实体提取等)
# 不会进行完整的PDF分析
```

**手动测试**:
```bash
# 进入容器
docker-compose -f docker-compose.test.yml exec test-env bash

# 测试基本功能
python -c "
from agents.interview.main import InterviewAnalystAgent
agent = InterviewAnalystAgent('test', 'test', 'test')
result = agent.assign_confidence_rating('I think I saw someone')
print(result)
"
```

---

## 📦 5. Logistics Agent 测试

**功能**: 生成后勤资源请求

**前置条件**: 无 (生成模拟数据)

```bash
# 测试Logistics Agent
./test_single_agent.sh logistics
```

**预期结果**:
- Redis中出现 `logistics.requests.raw` 流
- 包含资源请求 (医疗包、食物、水、燃料等)

---

## 🗺️ 6. Path Analysis Agent 测试

**功能**: 分析地形和路径规划

**前置条件**: 
- 需要 `GEMINI_API_KEY`
- DEM地形数据文件 `agents/path_analysis/data/slo_dem.tif`

```bash
# 检查DEM文件是否存在
ls agents/path_analysis/data/

# 测试Path Analysis Agent
./test_single_agent.sh path-analysis
```

**注意**: 这是最复杂的Agent，可能需要较长时间运行

---

## 🔍 调试和故障排除

### 查看Redis数据
```bash
# 使用脚本查看
./test_single_agent.sh redis

# 或直接连接Redis
docker-compose -f docker-compose.test.yml exec redis-test redis-cli

# 在Redis中查看流
XRANGE weather.forecast.raw - +
XRANGE health.assessment.raw - +
XRANGE photo.analysis.raw - +
```

### 进入测试容器调试
```bash
# 进入容器
docker-compose -f docker-compose.test.yml exec test-env bash

# 在容器内可以:
# 1. 手动运行Agent
python agents/weather/main.py

# 2. 测试Redis连接
python -c "import redis; r=redis.Redis(host='redis-test'); print(r.ping())"

# 3. 检查环境变量
env | grep API_KEY

# 4. 安装额外的调试工具
pip install ipython  # 交互式Python
```

### 查看日志
```bash
# 查看所有容器日志
docker-compose -f docker-compose.test.yml logs

# 查看特定容器日志
docker-compose -f docker-compose.test.yml logs test-env
docker-compose -f docker-compose.test.yml logs redis-test

# 实时跟踪日志
docker-compose -f docker-compose.test.yml logs -f test-env
```

### 常见问题

1. **API密钥错误**:
   ```bash
   # 检查.env文件
   cat .env | grep API_KEY
   
   # 重新设置环境
   ./test_single_agent.sh cleanup
   ./test_single_agent.sh setup
   ```

2. **Redis连接失败**:
   ```bash
   # 重启Redis
   docker-compose -f docker-compose.test.yml restart redis-test
   
   # 检查Redis状态
   docker-compose -f docker-compose.test.yml ps redis-test
   ```

3. **依赖包缺失**:
   ```bash
   # 重新构建镜像
   docker-compose -f docker-compose.test.yml build --no-cache
   ```

4. **文件权限问题**:
   ```bash
   # 检查文件权限
   ls -la input_images/
   ls -la data/transcripts/
   
   # 修复权限
   chmod 644 input_images/*
   chmod 644 data/transcripts/*
   ```

## 🎯 测试完成后的下一步

当所有单个Agent都测试通过后，你可以:

### 1. 启动完整系统
```bash
# 清理测试环境
./test_single_agent.sh cleanup

# 启动完整系统
./start_sar_system.sh full
```

### 2. 使用协调器管理
```bash
# 启动协调器
docker-compose --profile orchestrator up -d orchestrator

# 启动监控界面
docker-compose --profile monitoring up -d web-monitor
# 访问: http://localhost:5000
```

### 3. 集成测试
```bash
# 测试Agent间通信
# 1. 启动所有Agent
# 2. 添加测试图片
# 3. 观察各Agent如何响应和协作
```

## 📚 测试数据示例

### 测试图片准备
```bash
# 创建测试图片目录
mkdir -p input_images

# 可以使用的测试图片类型:
# - 包含人员的照片 (用于人员检测)
# - 户外场景 (用于地形分析)
# - 应急设备照片 (用于设备识别)
```

### 测试PDF准备
```bash
# 创建访谈记录目录
mkdir -p data/transcripts

# PDF文件应包含:
# - 访谈对话内容
# - 时间和地点信息
# - 人员描述
```

## 🏁 总结

通过这个测试流程，你可以:
1. ✅ 验证每个Agent的独立功能
2. ✅ 确认API密钥配置正确
3. ✅ 理解Agent的输入输出格式
4. ✅ 熟悉Redis数据流结构
5. ✅ 为整合系统做好准备

完成单Agent测试后，你就可以信心满满地启动完整的SAR多智能体系统了！