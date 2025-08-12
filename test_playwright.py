# test_playwright.py
from playwright.sync_api import sync_playwright

def test_pdf_generation():
    print("Bắt đầu kiểm tra Playwright...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.set_content("<h1>Chào thế giới!</h1><p>Nếu bạn thấy file PDF này, Playwright đã hoạt động.</p>")
            page.pdf(path="test_output.pdf")
            browser.close()
        print("✅ Hoàn tất! Đã tạo thành công file 'test_output.pdf'.")
        print("=> Môi trường Playwright của bạn đã sẵn sàng!")
    except Exception as e:
        print(f"❌ Đã xảy ra lỗi khi kiểm tra Playwright: {e}")

if __name__ == "__main__":
    test_pdf_generation()