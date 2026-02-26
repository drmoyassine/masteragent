FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install PyTorch CPU-only version first (saves ~2GB vs CUDA version)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install remaining Python dependencies
RUN pip install --no-cache-dir \
    fastapi==0.110.1 \
    uvicorn==0.25.0 \
    gliner==0.2.5 \
    transformers

COPY app.py .

# Expose port
EXPOSE 8002

# Run the server
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8002"]
