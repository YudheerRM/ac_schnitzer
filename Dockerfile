FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies (needed for lxml and some network tools)
RUN apt-get update && apt-get install -y \
    gcc \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all scripts
COPY . .

# Create directories for data and outputs if they don't exist
RUN mkdir -p data output

# Expose the Streamlit port (optional, but good to have ready)
EXPOSE 8501

# Expose the API port
EXPOSE 5000

# Default command (can be overridden in docker-compose)
CMD ["python", "src/scheduler.py"]
