# Dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md /app/
RUN pip install --no-cache-dir -e .

COPY edgepilot /app/edgepilot

CMD ["python", "-m", "edgepilot.mcp.server"]
