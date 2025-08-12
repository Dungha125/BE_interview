# ---- Giai đoạn 1: Cài đặt thư viện ----
# Dùng ảnh Python 3.11 gọn nhẹ
FROM python:3.13-slim as builder

# Tạo thư mục làm việc
WORKDIR /app

# Chép file requirements.txt vào trước
COPY requirements.txt .

# Cài đặt tất cả thư viện từ requirements.txt
RUN pip install --no-cache-dir --upgrade -r requirements.txt


# ---- Giai đoạn 2: Chạy ứng dụng ----
# Bắt đầu lại với một ảnh Python gọn nhẹ sạch sẽ
FROM python:3.11-slim

WORKDIR /app

# Sao chép các thư viện đã được cài ở giai đoạn 1 vào môi trường chạy
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Sao chép toàn bộ code của bạn vào
COPY . .

# Lệnh để chạy ứng dụng của bạn
# Railway sẽ tự động cung cấp biến $PORT
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "main:app", "--bind", "0.0.0.0:${PORT:-8080}"]