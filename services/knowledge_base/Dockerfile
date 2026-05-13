FROM python:3.11-slim

WORKDIR /app

COPY knowledge_base/requirements.txt ./
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn -r requirements.txt

COPY knowledge_base/app ./app
COPY knowledge_base/data ./data
COPY knowledge_base/init ./init

EXPOSE 8004

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]
