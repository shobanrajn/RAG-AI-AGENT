# Base image
FROM bom.ocir.io/bm2nhaouvzhw/baseimage-cholamandalam-com:python-3.11.6

WORKDIR /usr/src/app

# Copy application code
COPY . /usr/src/app/

# Install Nginx
RUN apt-get update && apt-get install -y --no-install-recommends nginx vim poppler-utils && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
ENV CMAKE_BUILD_PARALLEL_LEVEL=8
RUN pip install uv
RUN uv pip install --system --no-cache-dir -r requirements.txt
RUN uv pip install --system --no-cache-dir gunicorn


# Copy Nginx site config (you must provide this file in your project root)
COPY default /etc/nginx/sites-available/default

# Expose ports
EXPOSE 80

CMD uvicorn app.main:app --host 0.0.0.0 --port 5000 & \
    nginx -g 'daemon off;'
