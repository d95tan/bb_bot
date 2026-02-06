# Python base image
FROM python:3.11-slim

# Install Tesseract OCR and other dependencies
# Install Tesseract OCR and other dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1 \
    libglx-mesa0 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency files first (for better caching)
COPY pyproject.toml ./

# Copy application code
COPY src/ ./src/
COPY config/ ./config/

# Install Python dependencies (optionally dev deps for watchfiles hot-reload)
ARG INSTALL_DEV=false
RUN pip install --no-cache-dir . && \
    if [ "$INSTALL_DEV" = "true" ]; then pip install --no-cache-dir .[dev]; fi

# Create directory for debug output (optional)
RUN mkdir -p /app/debug

# Run the bot
CMD ["python", "-m", "src.main"]
