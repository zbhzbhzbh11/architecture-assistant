FROM python:3.11-slim

WORKDIR /app

COPY refactoring-agent/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY refactoring-agent/app ./app

EXPOSE 8005

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
