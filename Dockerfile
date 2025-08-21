# ---- Giai đoạn 1: Build ----
# Sử dụng Python 3.11 - phiên bản ổn định và được hỗ trợ rộng rãi
FROM python:3.11-slim as builder

# Cài đặt tất cả các dependencies hệ thống trong một lệnh duy nhất
# Bao gồm dependencies cho WeasyPrint VÀ Playwright
# Các gói được chọn lọc kỹ để phù hợp với python:3.11-slim (Debian)
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

# Thiết lập thư mục làm việc
WORKDIR /app

# Thêm đường dẫn cài đặt của pip vào biến môi trường PATH
ENV PATH="/usr/local/bin:${PATH}"

# Chép file requirements.txt vào
COPY requirements.txt .

# Cài đặt các thư viện Python
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Cài đặt các trình duyệt cần thiết cho Playwright
RUN playwright install --with-deps


# ---- Giai đoạn 2: Runtime ----
# Bắt đầu lại với một ảnh gọn nhẹ sạch sẽ, cùng phiên bản Python
FROM python:3.11-slim

# Cài đặt tất cả các thư viện hệ thống CẦN KHI CHẠY trong một lệnh duy nhất
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

# Sao chép các thư viện đã được cài ở giai đoạn 1
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Sao chép các browsers đã được cài đặt bởi Playwright
COPY --from=builder /root/.cache/ms-playwright /root/.cache/ms-playwright

# Lệnh để chạy ứng dụng
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "main:app", "--bind", "0.0.0.0:${PORT:-8080}"]
