FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    libaio1 wget unzip curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Build context is project root, so paths are relative to that
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source files
COPY backend/ .

# Bake frontend into image (volume mount in compose overrides at runtime)
COPY frontend/ /app/frontend/

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
