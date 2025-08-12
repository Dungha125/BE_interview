# ---- Giai đoạn 1: Build ----
# Sử dụng Python 3.11 - phiên bản ổn định và được hỗ trợ rộng rãi
FROM python:3.11-slim as builder

# THÊM BƯỚC NÀY: Cài đặt các công cụ build và thư viện hệ thống cần thiết
# - build-essential: Chứa các công cụ như gcc để biên dịch mã nguồn.
# - lib...: Các thư viện cần cho lxml và weasyprint.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

# Thiết lập thư mục làm việc
WORKDIR /app

# Chép file requirements.txt vào
COPY requirements.txt .

# Cài đặt các thư viện Python
RUN pip install --no-cache-dir --upgrade -r requirements.txt


# ---- Giai đoạn 2: Runtime ----
# Bắt đầu lại với một ảnh gọn nhẹ sạch sẽ, cùng phiên bản Python
FROM python:3.11-slim

# Cài đặt các thư viện hệ thống CẦN KHI CHẠY (cho weasyprint)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Sao chép các thư viện đã được cài ở giai đoạn 1
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Sao chép code của bạn vào
COPY . .

# Lệnh để chạy ứng dụng
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "main:app", "--bind", "0.0.0.0:${PORT:-8080}"]