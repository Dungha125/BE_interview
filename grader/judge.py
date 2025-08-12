import zipfile
import os
import shutil
import time
import json
import sys
import argparse
from pathlib import Path
from typing import List, Dict, Any
import uuid

from playwright.sync_api import sync_playwright, Page, Dialog, Error, \
    TimeoutError as PlaywrightTimeoutError

# <<< CẢI TIẾN >>>: Thêm thư viện cssutils để chuẩn hóa giá trị CSS tốt hơn trong tương lai (hiện tại chỉ dùng cho màu)
# Bạn có thể cần cài đặt: pip install cssutils
try:
    import cssutils

    # Tắt logging lỗi của cssutils để không làm nhiễu output
    cssutils.log.setLevel('CRITICAL')
except ImportError:
    cssutils = None
    print("[GraderScript] Cảnh báo: Thư viện 'cssutils' không được cài đặt. Khả năng chuẩn hóa màu sắc sẽ bị hạn chế.")


class SubmissionResultData:
    def __init__(self, test: str, result: str):
        self.test = test
        self.result = result

    def to_dict(self):
        return self.__dict__


def unzip_submission(zip_path: str, target_dir: str):
    os.makedirs(target_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(target_dir)
    print(f"[GraderScript] Đã giải nén {zip_path} sang {target_dir}")


# <<< CẢI TIẾN >>>: Mở rộng đáng kể hàm chuẩn hóa màu sắc
def _normalize_color(color_string: str) -> str:
    if not color_string:
        return ""

    # Sử dụng cssutils nếu có để phân tích màu chuyên nghiệp
    if cssutils:
        try:
            # Tạo một style rule tạm thời để parse
            sheet = cssutils.parseString(f'a {{ color: {color_string} }}')
            style = sheet.cssRules[0].style
            # Lấy giá trị rgb hoặc rgba
            if 'rgb' in style.color:
                return style.color.replace(" ", "")
        except Exception:
            # Nếu cssutils không parse được, quay lại phương pháp cũ
            pass

    # Phương pháp cũ dự phòng, mở rộng với nhiều màu hơn
    processed_string = color_string.lower().replace(" ", "")
    color_map = {
        # Tên màu cơ bản
        "green": "rgb(0,128,0)", "red": "rgb(255,0,0)", "blue": "rgb(0,0,255)",
        "yellow": "rgb(255,255,0)", "black": "rgb(0,0,0)", "white": "rgb(255,255,255)",
        "transparent": "rgba(0,0,0,0)", "grey": "rgb(128,128,128)",
        # Các màu phổ biến khác
        "lightblue": "rgb(173,216,230)", "darkgray": "rgb(169,169,169)",
        "lightgrey": "rgb(211,211,211)", "darkgrey": "rgb(169,169,169)",
        "purple": "rgb(128,0,128)", "orange": "rgb(255,165,0)", "pink": "rgb(255,192,203)",
        # Thêm các màu khác nếu cần
    }
    if processed_string in color_map:
        return color_map[processed_string]

    return processed_string.replace(" ", "")


# <<< CẢI TIẾN >>>: Mở rộng trigger với 'hover', 'submit', 'refresh'
def _execute_trigger_actions(page: Page, trigger_string: str):
    """
    Phân tích và thực thi một chuỗi các hành động trigger.
    Hỗ trợ: 'click:selector', 'input:selector=value', 'hover:selector', 'submit:selector', 'refresh'
    """
    if not trigger_string:
        return

    actions = [action.strip() for action in trigger_string.split(';')]
    print(f"[GraderScript]     Thực thi chuỗi {len(actions)} hành động trigger...")
    for i, action_str in enumerate(actions):
        print(f"[GraderScript]       Hành động {i + 1}: '{action_str}'")
        if action_str.startswith("click:"):
            selector = action_str.split("click:", 1)[1].strip()
            if not selector: raise ValueError("Selector trong trigger 'click' không được rỗng.")
            page.click(selector, timeout=5000)

        elif action_str.startswith("input:"):
            try:
                parts = action_str.split("=", 1)
                selector = parts[0].split("input:", 1)[1].strip()
                value_to_fill = parts[1]
                if not selector: raise ValueError("Selector trong trigger 'input' không được rỗng.")
                page.fill(selector, value_to_fill, timeout=5000)
            except (IndexError, ValueError) as e:
                raise ValueError(f"Định dạng trigger 'input' không hợp lệ: '{action_str}'. Lỗi: {e}")

        elif action_str.startswith("hover:"):  # Mới
            selector = action_str.split("hover:", 1)[1].strip()
            if not selector: raise ValueError("Selector trong trigger 'hover' không được rỗng.")
            page.hover(selector, timeout=5000)

        elif action_str.startswith("submit:"):  # Mới
            selector = action_str.split("submit:", 1)[1].strip()
            if not selector: raise ValueError("Selector trong trigger 'submit' không được rỗng.")
            page.eval_on_selector(selector, "form => form.submit()")

        elif action_str == "refresh":  # Mới
            page.reload(wait_until="networkidle")

        else:
            raise ValueError(f"Hành động trigger không được hỗ trợ: '{action_str}'")

        page.wait_for_timeout(300)  # Đợi một chút để UI cập nhật


def run_grading_logic(exercise_data: Dict[str, Any], index_path: Path) -> List[Dict[str, Any]]:
    results_list: List[SubmissionResultData] = []
    print(f"[GraderScript] Bắt đầu Playwright ĐỒNG BỘ để chấm điểm {index_path.resolve()}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            # <<< CẢI TIẾN >>>: Tải trang một lần duy nhất ở đầu
            initial_url = f"file://{index_path.resolve()}"
            page.goto(initial_url)
            page.wait_for_load_state('networkidle', timeout=15000)
            print(f"[GraderScript] Trang đã được tải lần đầu: {page.url}")

            testcases = exercise_data.get("frontend_testcases", exercise_data.get("testcases", []))
            exercise_id = exercise_data.get("id", "N/A")

            if not testcases:
                results_list.append(
                    SubmissionResultData(test="Setup", result="⚠️ Không có test case nào được định nghĩa."))

            for tc_data in testcases:
                tc_name = tc_data.get('name', f"Test Case Vô Danh {tc_data.get('id', '')}")
                tc_type = tc_data.get('type', 'unknown')
                tc_selector = tc_data.get('selector')
                tc_expected = tc_data.get('expected')
                tc_trigger = tc_data.get('trigger')
                tc_attribute_name = tc_data.get('attributeName')

                print(f"[GraderScript]   Đang chạy test case: '{tc_name}' (Loại: {tc_type})")

                try:
                    # <<< CẢI TIẾN QUẢN LÝ TRẠNG THÁI >>>
                    # Chỉ tải lại trang nếu test case không có trigger,
                    # để đảm bảo trạng thái được giữ nguyên cho các test case có tương tác.
                    if not tc_trigger:
                        print(f"[GraderScript]     Reset trạng thái trang (tải lại) cho test case không có trigger.")
                        page.reload(wait_until="networkidle")
                        page.wait_for_timeout(200)  # Đợi thêm chút cho ổn định

                    # 1. THỰC THI TRIGGER (TRỪ js_alert sẽ xử lý riêng)
                    if tc_type != "js_alert":
                        _execute_trigger_actions(page, tc_trigger)

                    # 2. THỰC HIỆN KIỂM TRA
                    if tc_type == "element_exists":
                        if not tc_selector: raise ValueError("Selector là bắt buộc")
                        element = page.query_selector(tc_selector)
                        if element and element.is_visible():
                            results_list.append(SubmissionResultData(test=tc_name, result="✅ Passed"))
                        else:
                            results_list.append(SubmissionResultData(test=tc_name,
                                                                     result=f"❌ Failed (Phần tử '{tc_selector}' không tồn tại hoặc không hiển thị)"))

                    elif tc_type == "text_equals":
                        if not tc_selector: raise ValueError("Selector là bắt buộc")
                        if tc_expected is None: raise ValueError("Expected text là bắt buộc")
                        element = page.query_selector(tc_selector)
                        actual_text = element.text_content().strip() if element else ""
                        expected_text = str(tc_expected).strip()
                        if actual_text == expected_text:
                            results_list.append(SubmissionResultData(test=tc_name, result="✅ Passed"))
                        else:
                            results_list.append(SubmissionResultData(test=tc_name,
                                                                     result=f"❌ Failed (Mong đợi text '{expected_text}', nhận được '{actual_text}')"))

                    # <<< THAY THẾ BẰNG ĐOẠN CODE NÀY >>>
                    elif tc_type == "attribute_equals":
                        if not tc_selector: raise ValueError("Selector là bắt buộc")
                        if not tc_attribute_name: raise ValueError("AttributeName là bắt buộc")
                        if tc_expected is None: raise ValueError("Expected value là bắt buộc")

                        locator = page.locator(tc_selector).first

                        # 💡 Cải tiến cốt lõi nằm ở đây
                        prop_to_query = tc_attribute_name.lower()
                        if prop_to_query == 'background':
                            print(
                                "[GraderScript]     Phát hiện 'background', tự động chuyển sang kiểm tra 'background-color'.")
                            prop_to_query = 'background-color'

                        # Xử lý các thuộc tính CSS
                        if "-" in prop_to_query or prop_to_query in ["color", "font-family", "font-size", "display",
                                                                     "visibility", "opacity", "width", "position",
                                                                     "bottom", "border-radius", "box-shadow", "padding",
                                                                     "margin", "text-align", "justify-content",
                                                                     "align-items", "grid-template-columns",
                                                                     "transition-property", "transition-duration"]:
                            actual_value = locator.evaluate(
                                f"el => window.getComputedStyle(el).getPropertyValue('{prop_to_query}')")
                            expected_to_compare = str(tc_expected)

                            if "color" in prop_to_query or "background" in prop_to_query:
                                actual_value = _normalize_color(actual_value)
                                expected_to_compare = _normalize_color(expected_to_compare)
                            else:
                                actual_value = actual_value.strip().replace('"', '')
                                expected_to_compare = expected_to_compare.strip().replace('"', '')

                        # Xử lý các thuộc tính HTML thông thường
                        else:
                            actual_value = locator.get_attribute(tc_attribute_name) or ""
                            expected_to_compare = str(tc_expected)
                            if tc_attribute_name == 'disabled':
                                actual_value = "true" if actual_value is not None else "false"

                        if actual_value == expected_to_compare:
                            results_list.append(SubmissionResultData(test=tc_name, result="✅ Passed"))
                        else:
                            # Sử dụng tc_attribute_name gốc để hiển thị lỗi cho người dùng
                            results_list.append(SubmissionResultData(test=tc_name,
                                                                     result=f"❌ Failed (Thuộc tính '{tc_attribute_name}': mong đợi '{expected_to_compare}', nhận được '{actual_value}')"))

                    # <<< CẢI TIẾN >>>: Đổi tên thành element_does_not_exist cho rõ ràng
                    elif tc_type == "element_does_not_exist" or tc_type == "element_not_exists":
                        if not tc_selector: raise ValueError("Selector là bắt buộc")
                        try:
                            # Chờ cho phần tử biến mất hoặc bị ẩn đi, timeout ngắn
                            page.locator(tc_selector).wait_for(state='hidden', timeout=2000)
                            results_list.append(SubmissionResultData(test=tc_name, result="✅ Passed"))
                        except PlaywrightTimeoutError:
                            results_list.append(SubmissionResultData(test=tc_name,
                                                                     result=f"❌ Failed (Phần tử '{tc_selector}' vẫn tồn tại/hiển thị)"))

                    elif tc_type == "url_contains":
                        if tc_expected is None: raise ValueError("Expected URL substring là bắt buộc")
                        if str(tc_expected) in page.url:
                            results_list.append(SubmissionResultData(test=tc_name, result="✅ Passed"))
                        else:
                            results_list.append(SubmissionResultData(test=tc_name,
                                                                     result=f"❌ Failed (URL mong đợi chứa '{tc_expected}', nhưng URL hiện tại là '{page.url}')"))

                    # <<< CẢI TIẾN >>>: Logic js_alert được viết lại hoàn toàn, an toàn và chính xác
                    elif tc_type == "js_alert":
                        if tc_expected is None: raise ValueError("Expected alert text là bắt buộc")

                        alert_message = None

                        def handle_dialog(dialog: Dialog):
                            nonlocal alert_message
                            alert_message = dialog.message
                            print(f"[GraderScript]     Bắt được dialog với message: '{alert_message}'")
                            dialog.dismiss()

                        # 1. Gắn trình nghe sự kiện TRƯỚC khi thực hiện hành động
                        page.once("dialog", handle_dialog)

                        # 2. Thực thi trigger
                        _execute_trigger_actions(page, tc_trigger)

                        # 3. Đợi và kiểm tra kết quả (với timeout ngắn)
                        page.wait_for_timeout(1000)  # Đợi 1s để dialog có thời gian xuất hiện

                        if alert_message is not None and alert_message.strip() == str(tc_expected).strip():
                            results_list.append(SubmissionResultData(test=tc_name, result="✅ Passed"))
                        else:
                            results_list.append(SubmissionResultData(test=tc_name,
                                                                     result=f"❌ Failed (Mong đợi alert '{tc_expected}', nhận được '{alert_message}')"))

                    else:
                        results_list.append(SubmissionResultData(test=tc_name,
                                                                 result=f"⚠️ Skipped (Loại test không xác định: {tc_type})"))


                except (Error, ValueError, Exception) as e:

                    error_detail = f"{type(e).__name__}: {str(e)}"

                    results_list.append(SubmissionResultData(test=tc_name, result=f"❌ Error: {error_detail}"))

            # <<< CẢI TIẾN >>>: Đóng browser ở cuối
            browser.close()

    except Exception as outer_exception:
        error_type_name = type(outer_exception).__name__
        error_message_detail = str(outer_exception)
        full_error_msg = f"{error_type_name}: {error_message_detail}" if error_message_detail else error_type_name
        print(f"[GraderScript] Lỗi nghiêm trọng trong run_grading_logic: {full_error_msg}")
        if not any(r.test == "Hệ thống chấm điểm" for r in results_list):
            results_list.append(SubmissionResultData(test="Hệ thống chấm điểm",
                                                     result=f"❌ Error: Lỗi Playwright setup - {full_error_msg}"))

    finally:
        print(f"[GraderScript] Kết thúc Playwright. Số kết quả: {len(results_list)}")

    return [r.to_dict() for r in results_list]


def main():
    parser = argparse.ArgumentParser(description="Chấm điểm bài nộp HTML/JS.")
    parser.add_argument("exercise_json_str", help="Một chuỗi JSON chứa thông tin bài tập (Exercise object).")
    parser.add_argument("zip_file_path", help="Đường dẫn đến file ZIP bài nộp.")
    parser.add_argument("output_file_path", help="Đường dẫn để ghi file JSON kết quả.")
    args = parser.parse_args()

    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception as e_enc:
            print(f"[GraderScript] Warning: Không thể reconfigure stdout/stderr encoding: {e_enc}", file=sys.stderr)

    print(f"[GraderScript] Nhận được zip_file_path: {args.zip_file_path}")
    print(f"[GraderScript] Nhận được output_file_path: {args.output_file_path}")

    results_for_json = []
    extract_dir = None

    try:
        exercise_data = json.loads(args.exercise_json_str)
        # <<< CẢI TIẾN >>>: Đổi tên thư mục giải nén để dễ debug hơn
        exercise_id = exercise_data.get("id", "unknown_id")
        timestamp = str(int(time.time()))
        base_submissions_dir = Path(__file__).resolve().parent / "temp_submissions"
        base_submissions_dir.mkdir(exist_ok=True)
        unique_folder_name = f"exercise-{exercise_id}_{timestamp}"
        extract_dir = base_submissions_dir / unique_folder_name

        unzip_submission(args.zip_file_path, str(extract_dir))
        index_path = extract_dir / "index.html"

        if not index_path.exists():
            # Thử tìm các file html khác nếu không có index.html
            html_files = list(extract_dir.glob('*.html'))
            if not html_files:
                print(f"[GraderScript] Lỗi: Không tìm thấy file .html nào trong {extract_dir}")
                results_for_json = [SubmissionResultData(test="Thiết lập",
                                                         result="❌ Error: Không tìm thấy file .html nào trong bài nộp.").to_dict()]
            else:
                index_path = html_files[0]
                print(
                    f"[GraderScript] Cảnh báo: không tìm thấy 'index.html', sử dụng file '{index_path.name}' thay thế.")
                results_for_json = run_grading_logic(exercise_data, index_path)
        else:
            results_for_json = run_grading_logic(exercise_data, index_path)

    except json.JSONDecodeError as e:
        results_for_json = [
            SubmissionResultData(test="Setup Error", result=f"❌ Error: Lỗi định dạng JSON của bài tập - {e}").to_dict()]
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        print(f"[GraderScript] Lỗi không xác định trong main(): {error_msg}")
        if not results_for_json: results_for_json = []
        results_for_json.append(SubmissionResultData(test="System Error", result=f"❌ Error: {error_msg}").to_dict())
    finally:
        if extract_dir and extract_dir.exists():
            try:
                # Giữ lại thư mục nếu có lỗi để debug, xóa nếu chạy thành công
                if any("Error" in r['result'] for r in results_for_json):
                    print(f"[GraderScript] Phát hiện lỗi, giữ lại thư mục để debug: {extract_dir}")
                else:
                    shutil.rmtree(extract_dir)
                    print(f"[GraderScript] Đã dọn dẹp thư mục thành công: {extract_dir}")
            except OSError as e_rm:
                print(f"[GraderScript] Lỗi khi dọn dẹp thư mục {extract_dir}: {e_rm}")

        try:
            with open(args.output_file_path, 'w', encoding='utf-8') as f:
                json.dump(results_for_json, f, ensure_ascii=False, indent=4)
            print(f"[GraderScript] Đã ghi kết quả vào {args.output_file_path}")
        except Exception as e_write:
            print(f"[GraderScript] Lỗi khi ghi file kết quả {args.output_file_path}: {e_write}")
            # In ra console nếu không ghi được file
            print("---RESULTS_START---")
            print(json.dumps(results_for_json, ensure_ascii=False, indent=4))
            print("---RESULTS_END---")


if __name__ == "__main__":
    main()