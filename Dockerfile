# 1. Use an official Python runtime as a parent image
FROM python:3.12-slim

# 2. Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV APP_HOME=/app

# 3. Set the working directory in the container
WORKDIR $APP_HOME

# 4. Install system dependencies required by Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    # List of dependencies for Playwright browsers (Chrome, Firefox, WebKit)
    libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libatspi2.0-0 libxcomposite1 libxrandr2 libgbm1 libxkbcommon0 libpango-1.0-0 libcairo2 libasound2 libxtst6 \
    # Clean up apt cache to reduce image size
    && rm -rf /var/lib/apt/lists/*

# 5. Install Python dependencies
# First, copy only the requirements file to leverage Docker cache
COPY requirements.txt .
# Install gunicorn and other dependencies
RUN pip install --no-cache-dir -r requirements.txt

# 6. Install Playwright browsers
# This must be done AFTER pip install
RUN playwright install --with-deps

# 7. Copy the application source code into the container
COPY . .

# 8. Define the command to run the application
# Use gunicorn for production. It's a robust WSGI server.
# --workers 1 is standard for Cloud Run's single-core instances.
# --threads 8 handles concurrent requests efficiently.
# --timeout 0 disables gunicorn's timeout to let Cloud Run manage it.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "0", "main:app"]