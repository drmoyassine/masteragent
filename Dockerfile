# Multi-stage Dockerfile for PromptSRC
# Stage 1: Build Frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# Copy package files (yarn.lock is optional)
COPY frontend/package.json ./
COPY frontend/yarn.lock* ./

# Install dependencies
RUN yarn install

# Copy frontend source
COPY frontend/ ./

# Build frontend
ARG REACT_APP_BACKEND_URL
ENV REACT_APP_BACKEND_URL=${REACT_APP_BACKEND_URL}
RUN yarn build

# Stage 2: Python Backend with built frontend
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    supervisor \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy backend requirements and install Python dependencies
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend source
COPY backend/ ./backend/

# Copy built frontend from builder stage
COPY --from=frontend-builder /app/frontend/build ./frontend/build

# Create nginx configuration
RUN echo 'server { \n\
    listen 80; \n\
    server_name _; \n\
    \n\
    location /api { \n\
        proxy_pass http://127.0.0.1:8001; \n\
        proxy_set_header Host $host; \n\
        proxy_set_header X-Real-IP $remote_addr; \n\
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; \n\
        proxy_set_header X-Forwarded-Proto $scheme; \n\
        proxy_connect_timeout 60s; \n\
        proxy_send_timeout 60s; \n\
        proxy_read_timeout 60s; \n\
    } \n\
    \n\
    location / { \n\
        root /app/frontend/build; \n\
        try_files $uri $uri/ /index.html; \n\
    } \n\
}' > /etc/nginx/sites-available/default

# Create supervisord configuration
RUN echo '[supervisord] \n\
nodaemon=true \n\
logfile=/var/log/supervisor/supervisord.log \n\
pidfile=/var/run/supervisord.pid \n\
\n\
[program:nginx] \n\
command=nginx -g "daemon off;" \n\
autostart=true \n\
autorestart=true \n\
stdout_logfile=/dev/stdout \n\
stdout_logfile_maxbytes=0 \n\
stderr_logfile=/dev/stderr \n\
stderr_logfile_maxbytes=0 \n\
\n\
[program:backend] \n\
command=python -m uvicorn server:app --host 0.0.0.0 --port 8001 \n\
directory=/app/backend \n\
autostart=true \n\
autorestart=true \n\
stdout_logfile=/dev/stdout \n\
stdout_logfile_maxbytes=0 \n\
stderr_logfile=/dev/stderr \n\
stderr_logfile_maxbytes=0' > /etc/supervisor/conf.d/app.conf

# Create log directory
RUN mkdir -p /var/log/supervisor

# Expose port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost/api/health || exit 1

# Start supervisord
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf"]
