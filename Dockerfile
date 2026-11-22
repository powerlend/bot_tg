FROM python:3.11-slim

# Версія Litestream (інструмент, що постійно копіює базу SQLite в хмару)
ARG LITESTREAM_VERSION=0.3.13

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL -o /tmp/litestream.tar.gz \
      "https://github.com/benbjohnson/litestream/releases/download/v${LITESTREAM_VERSION}/litestream-v${LITESTREAM_VERSION}-linux-amd64.tar.gz" \
    && tar -C /usr/local/bin -xzf /tmp/litestream.tar.gz \
    && rm /tmp/litestream.tar.gz \
    && litestream version

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# На випадок, якщо файл збережено з Windows-переносами рядків (CRLF)
RUN sed -i 's/\r$//' docker-entrypoint.sh litestream.yml && chmod +x docker-entrypoint.sh

ENV PYTHONUNBUFFERED=1

CMD ["./docker-entrypoint.sh"]
