FROM python:3.10-slim

WORKDIR /workspace

# Install git for pip git+https:// installs
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY agents/mission_controller/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install shared package
RUN pip install git+https://github.com/RandomCyberCoder/Agentic-MVP-Shared.git

# Copy agent code
COPY agents/mission_controller/ ./agents/mission_controller/

ENV PYTHONPATH=/workspace

CMD ["python", "-m", "agents.mission_controller.main"]
