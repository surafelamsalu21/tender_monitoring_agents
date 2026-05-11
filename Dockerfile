# Backend API + Playwright on Linux (avoids Windows asyncio + browser driver issues).
# Base image ships Chromium-compatible OS deps; pip may upgrade playwright — reinstall browser.
FROM mcr.microsoft.com/playwright/python:v1.59.0-noble

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install chromium

COPY . .

EXPOSE 8000

# No --reload: stable default for containers. Set DEBUG in .env only if you need it.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
