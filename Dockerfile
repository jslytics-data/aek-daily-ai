# 1. Use an official Python runtime as a parent image
FROM python:3.12-slim

# 2. Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV APP_HOME=/app

# 3. Set the working directory in the container
WORKDIR $APP_HOME

# 4. Install system dependencies
# These are general dependencies, kept minimal.
# curl-cffi and other libraries may need some of these.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 \
    && rm -rf /var/lib/apt/lists/*

# 5. Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy the application source code into the container
COPY . .

# 7. Define the command to run the application
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "0", "main:app"]