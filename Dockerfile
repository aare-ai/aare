FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for z3
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create ontologies directory
RUN mkdir -p /app/ontologies

# Set environment variables
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV ONTOLOGY_DIR=/app/ontologies

# Expose the port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run with gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "--timeout", "30", "app:app"]
