# PulseIQ backend — Linux container used by docker-compose.yml.
# Purpose: parity environment where Windows Application Control does not apply.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir \
       https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl \
    || pip install --no-cache-dir -r requirements.txt

# Source (agents/, backend/) is copied; models/ and data/ are bind-mounted
# read-only by docker-compose so the artifact stays single-sourced.
COPY agents ./agents
COPY backend ./backend

EXPOSE 8000

# BACKEND_CORS_ORIGINS is consumed when api_server is updated for it;
# until then the dev posture (allow_origins=["*"]) applies inside the container too.
CMD ["python", "-m", "uvicorn", "backend.api_server:app", "--host", "0.0.0.0", "--port", "8000"]
