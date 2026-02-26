FROM python:3.12-slim

RUN pip install uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY src/ ./src/
COPY state.json ./

ENTRYPOINT ["uv", "run", "python", "-m", "cpp_bot.main"]
