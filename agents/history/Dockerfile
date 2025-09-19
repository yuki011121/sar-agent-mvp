FROM python:3.10-slim
WORKDIR /workspace
COPY poetry.lock pyproject.toml ./
COPY agents/history/main.py  ./agents/history/
COPY agents/history/models/isrid_tfidf_vectorizer.joblib  ./agents/history/models/
RUN pip install --no-cache-dir poetry~=1.8.0 && poetry install
CMD ["sleep", "infinity"]