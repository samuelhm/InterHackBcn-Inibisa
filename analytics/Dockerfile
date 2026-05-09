FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies (cached layer)
COPY analytics/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy analytics package → /app/analytics/
COPY analytics/ /app/analytics/

ENV PYTHONUNBUFFERED=1

CMD ["python", "/app/analytics/main.py"]
