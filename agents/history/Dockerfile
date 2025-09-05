FROM python:3.10-slim
WORKDIR /workspace
COPY poetry.lock pyproject.toml ./
COPY agents/history ./agents/history
RUN pip install --no-cache-dir poetry~=1.8.0 && poetry install
CMD ["sleep", "infinity"]