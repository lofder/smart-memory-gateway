FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY config.yaml config.yaml

ENV ENGRAM_CONFIG=/app/config.yaml
ENV NO_PROXY=localhost,127.0.0.1,qdrant
ENV no_proxy=localhost,127.0.0.1,qdrant

ENTRYPOINT ["python", "src/server.py"]
