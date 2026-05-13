FROM python:3.10-slim

WORKDIR /workspace

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    google-generativeai \
    redis \
    python-dotenv \
    neo4j \
    plotly \
    kaleido \
    pandas \
    numpy \
    scipy

RUN pip install --no-cache-dir git+https://github.com/RandomCyberCoder/Agentic-MVP-Shared.git

COPY agents/cluemeister ./agents/cluemeister
COPY agents/base_agent.py ./agents/base_agent.py

RUN mkdir -p /workspace/agents/cluemeister/data
COPY agents/MAKE2026/data/processed/probability_kg.json \
     /workspace/agents/cluemeister/data/probability_kg.json

ENV PYTHONPATH=/workspace
ENV REDIS_URL=redis://redis:6379

WORKDIR /workspace/agents/cluemeister

CMD ["python", "main.py"]
