FROM python:3.10-slim
WORKDIR /workspace
RUN apt update && apt install -y pipx && pipx install poetry
ENV PATH="/root/.local/bin:$PATH"
RUN poetry --version
COPY poetry.lock pyproject.toml ./
COPY .env ./
COPY agents/history/main.py  ./agents/history/
COPY agents/history/models/isrid_tfidf_vectorizer.joblib  ./agents/history/models/
CMD ["sleep", "infinity"]