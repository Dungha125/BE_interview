# file_parser.py (phiên bản cuối cùng, tích hợp OCR)

import re
from pathlib import Path

# Thư viện cho OCR
try:
    import pytesseract
    from PIL import Image
except ImportError:
    pytesseract = None
    Image = None

# Thư viện đọc file
try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    from docx import Document
except ImportError:
    Document = None


def ocr_from_pdf(file_path: Path) -> str:
    """
    Sử dụng Tesseract OCR để trích xuất văn bản từ các trang PDF.
    Đây là giải pháp dự phòng khi get_text() thông thường thất bại.
    """
    if not pytesseract or not Image:
        raise ImportError(
            "Thư viện pytesseract hoặc pillow chưa được cài đặt. Vui lòng chạy: pip install pytesseract pillow")

    text = ""
    doc = fitz.open(file_path)
    print(f"OCR: Bắt đầu xử lý {len(doc)} trang bằng Tesseract...")

    for i, page in enumerate(doc):
        # Render trang thành hình ảnh
        pix = page.get_pixmap(dpi=300)  # DPI cao hơn cho kết quả OCR tốt hơn
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        # Sử dụng tesseract để đọc text từ ảnh
        # lang='vie+eng' để nhận diện cả tiếng Việt và tiếng Anh
        page_text = pytesseract.image_to_string(img, lang='vie+eng')
        print(f"OCR: Trang {i + 1} đã xử lý xong.")
        if page_text:
            text += page_text + "\n"

    print("OCR: Hoàn tất.")
    return text


def extract_text(file_path: Path) -> str:
    """
    Trích xuất nội dung text, tự động chuyển sang OCR nếu cần.
    """
    ext = file_path.suffix.lower()
    text = ""

    try:
        if ext == ".txt":
            text = file_path.read_text(encoding="utf-8")

        elif ext == ".pdf":
            if not fitz:
                raise ImportError("PyMuPDF chưa được cài đặt.")

            with fitz.open(file_path) as doc:
                for page in doc:
                    text += page.get_text() + "\n"

            # KIỂM TRA: Nếu get_text() không hiệu quả, chuyển sang OCR
            if len(text.strip()) < 100:  # Đặt một ngưỡng ký tự hợp lý
                print("Cảnh báo: PyMuPDF get_text() không hiệu quả, đang chuyển sang OCR...")
                text = ocr_from_pdf(file_path)

        elif ext == ".docx":
            if not Document:
                raise ImportError("python-docx chưa được cài đặt.")
            doc = Document(file_path)
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"

    except Exception as e:
        print(f"Lỗi khi đọc file {file_path}: {e}")
        return ""

    cleaned_text = re.sub(r'[\r\n\t]+', ' ', text)  # Làm sạch các ký tự xuống dòng, tab
    cleaned_text = re.sub(r' +', ' ', cleaned_text)  # Thay thế nhiều khoảng trắng bằng một

    return cleaned_text.strip()