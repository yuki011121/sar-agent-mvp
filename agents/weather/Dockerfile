# Weather Agent 独立Docker配置
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制requirements
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制共享模块
COPY ../../shared ./shared

# 复制Agent代码
COPY . ./agents/weather

# 设置环境变量
ENV PYTHONPATH=/app
ENV AGENT_NAME=weather-agent
ENV AGENT_VERSION=1.1

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# 运行Agent
CMD ["python", "agents/weather/main.py"]