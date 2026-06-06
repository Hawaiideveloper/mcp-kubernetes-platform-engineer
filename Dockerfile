FROM python:3.11-slim
LABEL org.opencontainers.image.source=https://github.com/Hawaiideveloper/mcp-kubernetes-platform-engineer
WORKDIR /app
RUN apt-get update -qq  && apt-get install -y --no-install-recommends ca-certificates curl  && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt psycopg[binary] pytest-asyncio ||     pip install --no-cache-dir kubernetes>=28 PyYAML>=6 pydantic>=2 httpx>=0.25 anyio>=4
COPY src/ /app/src/
COPY pytest.ini /app/pytest.ini
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1
USER 65532
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD python3 -c "import importlib; importlib.import_module(\"auto_remediate\")" || exit 1
CMD ["python3", "-m", "auto_remediate.runtime"]
