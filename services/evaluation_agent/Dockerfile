FROM python:3.11-slim

WORKDIR /app

COPY evaluation-agent/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY common ./common
COPY evaluation-agent/app ./app

EXPOSE 8003

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
