FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY . .

ENV GREENSTREEM_HOST=0.0.0.0
ENV GREENSTREEM_PORT=8097
ENV GREENSTREEM_SESSION_TTL_SECONDS=43200

EXPOSE 8097

CMD ["python", "server.py"]
