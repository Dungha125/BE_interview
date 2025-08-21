# ---- Giai đoạn 1: Build ----
FROM python:3.11-slim as builder

# Cài đặt tất cả các dependencies hệ thống trong một lệnh duy nhất
# Bao gồm cả WeasyPrint và Playwright dependencies
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
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm-dev \
    libasound2 \
    libgdk-pixbuf2.0-0 \
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
    libwebp-dev \
    libxrender1 \
    libxshmfence1 \
    libatspi2.0-0 \
    libgstreamer-plugins-good1.0-0 \
    libpulse0 \
    && rm -rf /var/lib/apt/lists/*

# Thiết lập thư mục làm việc
WORKDIR /app

# Chép file requirements.txt vào
COPY requirements.txt .

# Cài đặt các thư viện Python và Playwright's browsers
RUN pip install --no-cache-dir --upgrade -r requirements.txt
RUN playwright install --with-deps

# Sao chép code của bạn vào
COPY . .


# ---- Giai đoạn 2: Runtime ----
FROM python:3.11-slim

# Cài đặt các thư viện hệ thống CẦN KHI CHẠY trong một lệnh duy nhất
# Bao gồm dependencies cho WeasyPrint VÀ Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    fonts-dejavu \
    libnss3 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm-dev \
    libasound2 \
    libgdk-pixbuf2.0-0 \
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
    libwebp-dev \
    libxrender1 \
    libxshmfence1 \
    libatspi2.0-0 \
    libgstreamer-plugins-good1.0-0 \
    libpulse0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Sao chép các thư viện Python
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Sao chép các browsers đã được cài đặt bởi Playwright
COPY --from=builder /root/.cache/ms-playwright /root/.cache/ms-playwright

# Sao chép code của bạn vào
COPY . .

# Lệnh để chạy ứng dụng
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "main:app", "--bind", "0.0.0.0:${PORT:-8080}"]
