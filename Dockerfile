FROM python:3.11-slim

ARG TARGETARCH

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates curl \
    && curl -fsSL -o /usr/local/bin/kubectl \
    "https://dl.k8s.io/release/v1.31.4/bin/linux/${TARGETARCH:-amd64}/kubectl" \
    && chmod +x /usr/local/bin/kubectl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY engine ./engine
COPY worlds ./worlds
COPY progress.json ./progress.json

ENV K8SQUEST_WEB=true

CMD ["python", "engine/engine.py"]