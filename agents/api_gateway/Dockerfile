FROM python:3.10-slim

WORKDIR /workspace

# Install git for pip git+https:// installs
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY agents/api_gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install shared package
RUN pip install git+https://github.com/RandomCyberCoder/Agentic-MVP-Shared.git

# Copy agent code
COPY agents/api_gateway/ ./agents/api_gateway/

ENV PYTHONPATH=/workspace
ENV API_HOST=0.0.0.0
ENV API_PORT=8080

EXPOSE 8080

CMD ["python", "-m", "agents.api_gateway.main"]
