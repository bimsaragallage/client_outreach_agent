# Base Python Environment
FROM python:3.11-slim AS base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Working directory inside container
WORKDIR /app

# Install system dependencies for building packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the API port
EXPOSE 8080

# Create directories (safety in case they're empty)
RUN mkdir -p data/campaigns data/leads data/memory data/uploaded_leads logs

# Default start command: run FastAPI app
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8080"]