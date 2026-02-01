# Dockerfile for Financial Analysis Agent
# Lightweight image for running quarterly_earnings_price_tracker.sh

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
# - Chromium for Selenium web scraping (works on both amd64 and arm64)
# - Other build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for better layer caching)
COPY requirements-minimal.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements-minimal.txt

# Copy the entire project
COPY . .

# Make shell scripts executable
RUN chmod +x *.sh

# Create data directories
RUN mkdir -p /app/data /app/.cache

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Chromium configuration for running in container
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# Default command - run the tracker in foreground mode
# Override with: docker run ... bash (for interactive)
CMD ["bash", "-c", "./quarterly_earnings_price_tracker.sh start && tail -f quarterly_earnings_price_tracker.log"]
