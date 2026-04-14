# services/weather_api/Dockerfile
FROM python:3.11-slim
WORKDIR /app

# install deps
COPY services/weather_api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# copy the entire repo (so 'agents/' code is available)
COPY . /app

EXPOSE 8000
CMD ["uvicorn", "services.weather_api.app:app", "--host", "0.0.0.0", "--port", "8000"]
