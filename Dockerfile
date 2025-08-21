# ---- Giai đoạn 1: Build ----
FROM python:3.11-slim as builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    fonts-dejavu \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm-dev \
    libasound2 \
    libgdk-pixbuf-xlib-2.0-0 \
    libjpeg-dev \
    libpng-dev \
    libwebp-dev \
    libx11-6 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libxtst6 \
    libglib2.0-0 \
    libdbus-1-3 \
    libgstreamer-plugins-base1.0-0 \
    libgstreamer1.0-0 \
    libxrender1 \
    libxshmfence1 \
    libatspi2.0-0 \
    libpulse0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .

# Cài đặt requirements + playwright
# Cài đặt requirements
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Cài playwright
RUN pip install --no-cache-dir playwright

# Cài browsers + deps (chromium, hoặc firefox/webkit nếu cần)
#RUN playwright install --with-deps chromium



# ---- Giai đoạn 2: Runtime ----
FROM python:3.11-slim

# Cài system deps cần cho playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    fonts-dejavu \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm-dev \
    libasound2 \
    libgdk-pixbuf-xlib-2.0-0 \
    libjpeg-dev \
    libpng-dev \
    libwebp-dev \
    libx11-6 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libxtst6 \
    libglib2.0-0 \
    libdbus-1-3 \
    libgstreamer-plugins-base1.0-0 \
    libgstreamer1.0-0 \
    libxrender1 \
    libxshmfence1 \
    libatspi2.0-0 \
    libpulse0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy packages từ builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Cài browsers trong runtime
RUN playwright install chromium


# Lệnh để chạy ứng dụng
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "main:app", "--bind", "0.0.0.0:${PORT:-8080}"]
