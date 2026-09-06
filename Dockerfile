FROM python:3.14-slim

RUN pip install uv

WORKDIR /app

COPY pyproject.toml uv.lock src ./
RUN uv sync --frozen --no-dev

ENV STORAGE_DIR=/data/state
ENV LOG_DIR=/data/logs
ENV GOOGLE_CREDENTIALS_PATH=/data/credentials.json
ENV GITHUB_APP_PRIVATE_KEY_PATH=/data/github-app.pem

VOLUME ["/data"]

ENTRYPOINT ["uv", "run", "python", "-m", "itmogus.app.main"]
