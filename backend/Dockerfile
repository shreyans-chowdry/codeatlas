# Build context is the PROJECT ROOT (see docker-compose.yml) so the
# `backend` package path used in imports (backend.app...) exists in the image.
FROM python:3.12-slim

# git is needed to clone repos; build-essential for any C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend ./backend

ENV PYTHONPATH=/app
EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
