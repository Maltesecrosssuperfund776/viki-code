FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY . /app
RUN pip install --no-cache-dir -e .

RUN mkdir -p /workspace
WORKDIR /workspace

CMD ["viki", "--help"]
