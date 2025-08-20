import sys
import json
import os
import re
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

from fpdf import FPDF, FPDFException
import jinja2
from weasyprint import HTML
import google.generativeai as genai
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Đảm bảo in Unicode ra stdout (Windows)
sys.stdout.reconfigure(encoding='utf-8')

# --- ĐĂNG KÝ FONT (PHẦN QUAN TRỌNG NHẤT) ---
try:
    BASE_DIR = Path(__file__).resolve().parent
    ROBOTO_REGULAR_PATH = BASE_DIR / 'Roboto-Regular.ttf'
    ROBOTO_BOLD_PATH = BASE_DIR / 'Roboto-Bold.ttf'
    ROBOTO_ITALIC_PATH = BASE_DIR / 'Roboto-Italic.ttf'
    ROBOTO_BOLDITALIC_PATH = BASE_DIR / 'Roboto-BoldItalic.ttf'

    # Đăng ký từng file font
    pdfmetrics.registerFont(TTFont('Roboto', ROBOTO_REGULAR_PATH))
    pdfmetrics.registerFont(TTFont('Roboto-Bold', ROBOTO_BOLD_PATH))
    pdfmetrics.registerFont(TTFont('Roboto-Italic', ROBOTO_ITALIC_PATH))
    pdfmetrics.registerFont(TTFont('Roboto-BoldItalic', ROBOTO_BOLDITALIC_PATH))

    # Đăng ký font family hoàn chỉnh
    pdfmetrics.registerFontFamily(
        'Roboto',
        normal='Roboto',
        bold='Roboto-Bold',
        italic='Roboto-Italic',
        boldItalic='Roboto-BoldItalic'
    )
    print("Đăng ký font Roboto thành công.")
except Exception as e:
    print(f"LỖI NGHIÊM TRỌNG: Không thể đăng ký font. File PDF sẽ bị lỗi font. Lỗi: {e}", file=sys.stderr)
# --- KẾT THÚC ĐĂNG KÝ FONT ---


def clear_special_tokens(text):
    return re.sub(r'[^\x20-\x7E]+', ' ', text)


def remove_special_tokens(text):
    text = re.sub(r'\\n', ' ', text)
    text = re.sub(r'\\t', ' ', text)
    text = re.sub(r'\\r', ' ', text)
    text = re.sub(r'\\', '', text)
    return text


def _call_gemini_model(prompt_text, api_key, model_name="gemini-1.5-flash", temperature=0.0,
                       response_mime_type="text/plain"):
    """Internal helper to call Gemini API."""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]
    generation_config = genai.types.GenerationConfig(temperature=temperature, response_mime_type=response_mime_type)
    response = model.generate_content(prompt_text, generation_config=generation_config, safety_settings=safety_settings)

    if not response.parts:
        raise ValueError("Gemini did not return valid content.")

    raw_text_response = response.text.strip()
    return raw_text_response


def extract_detailed_cv_info(cv_text: str, api_key: str) -> dict:
    """
    Extracts detailed CV information using Gemini.
    """
    extract_prompt = f"""
    Đọc nội dung CV dưới đây và trích xuất thông tin thành JSON với các trường:
    "Name": Tên đầy đủ của ứng viên.
    "Email": Địa chỉ email.
    "Phone": Số điện thoại.
    "Job_Position": Vị trí công việc ứng viên đang nhắm tới hoặc vị trí gần nhất.
    "Skills": Danh sách các kỹ năng kỹ thuật (ngôn ngữ, framework, công cụ, database...).
    "Education": Danh sách thông tin học vấn, mỗi mục là một đối tượng JSON với các trường: school, major, degree, year.
    "Experience": Danh sách kinh nghiệm làm việc, mỗi mục là một đối tượng JSON với các trường: company, position, time, description.
    "Certification": Danh sách các chứng chỉ đã đạt được (chỉ tên chứng chỉ).
    "Projects": Danh sách các dự án đã tham gia, mỗi mục là một đối tượng JSON với các trường: name, description, role, technologies (danh sách chuỗi).
    "Summary": Tóm tắt bản thân hoặc mục tiêu nghề nghiệp.

    Chỉ trả về JSON, không giải thích thêm, không markdown.
    **Tất cả nội dung trong JSON phải bằng tiếng Việt.**

    CV:
    {cv_text}
    """
    raw_json = _call_gemini_model(extract_prompt, api_key, temperature=0.0, response_mime_type="application/json")

    # Clean and parse JSON
    raw_json = re.sub(r"^```json[\r\n]*", "", raw_json)
    raw_json = re.sub(r"^```[\r\n]*", "", raw_json)
    raw_json = re.sub(r"```[\r\n]*$", "", raw_json)
    raw_json = raw_json.strip()

    parsed_data = {}
    try:
        parsed_data = json.loads(raw_json)
    except json.JSONDecodeError:
        # Fallback for malformed JSON, try to find JSON-like string
        match = re.search(r"\{.*\}", raw_json, re.DOTALL)
        if match:
            try:
                parsed_data = json.loads(match.group(0))
            except json.JSONDecodeError:
                return {"error": "Không parse được JSON gốc từ Gemini", "raw_response": raw_json}
        else:
            return {"error": "Không tìm thấy JSON trong phản hồi của Gemini", "raw_response": raw_json}

    # --- NEW: Robust parsing and normalization for nested lists of dictionaries ---
    for field in ["Education", "Experience", "Projects"]:
        if field in parsed_data and isinstance(parsed_data[field], list):
            processed_list = []
            for item in parsed_data[field]:
                if isinstance(item, str):
                    try:
                        # Attempt to parse stringified JSON objects within the list
                        parsed_item = json.loads(item)
                        processed_list.append(parsed_item)
                    except json.JSONDecodeError:
                        # If it's a string but not valid JSON, try to handle as plain text or skip
                        # For now, we'll try to include it as a string, but it might still cause Pydantic issues
                        # A better approach might be to log and skip, or try more robust string parsing
                        processed_list.append(item)
                elif isinstance(item, dict):
                    # Ensure all values within nested dicts are not None if Pydantic expects string
                    # And handle 'technologies' specifically for Projects
                    cleaned_item = {k: (v if v is not None else "") for k, v in item.items()}
                    if field == "Projects" and "technologies" in cleaned_item:
                        if cleaned_item["technologies"] is None:
                            cleaned_item["technologies"] = []
                        elif not isinstance(cleaned_item["technologies"], list):
                            # If technologies is a string, try to split it or convert to list
                            cleaned_item["technologies"] = [str(cleaned_item["technologies"])]
                    processed_list.append(cleaned_item)
                else:
                    processed_list.append(item)  # Keep as is if already a dict/other type
            parsed_data[field] = processed_list
        elif field in parsed_data and parsed_data[field] is None:
            # If the field itself is None, ensure it's an empty list for Pydantic compatibility
            parsed_data[field] = []
    # --- END NEW ---

    # Ensure top-level string fields are not None if Pydantic expects string
    for key in ["Name", "Email", "Phone", "Job_Position", "Summary"]:
        if key in parsed_data and parsed_data[key] is None:
            parsed_data[key] = ""

    # Ensure Skills and Certification are lists, even if None
    if "Skills" in parsed_data and parsed_data["Skills"] is None:
        parsed_data["Skills"] = []
    if "Certification" in parsed_data and parsed_data["Certification"] is None:
        parsed_data["Certification"] = []

    return parsed_data


def compare_and_identify_gaps(user_extracted_info: dict, target_job_position: str, api_key: str) -> dict:
    """
    Compares user's extracted info against an ideal profile for a target job position
    to identify missing and extra skills/experiences.
    """
    # Combine all skills from user_extracted_info for comparison
    user_skills_list = []
    if user_extracted_info.get("Skills"):
        user_skills_list.extend(user_extracted_info["Skills"])
    # You might want to add other relevant fields like technologies from projects/experience
    # For now, let's keep it simple with "Skills" field

    # Convert complex objects in Education/Experience to simple strings for the prompt
    education_str = ", ".join([str(e) for e in user_extracted_info.get('Education', [])])
    experience_str = ", ".join([str(e) for e in user_extracted_info.get('Experience', [])])

    user_profile_summary = f"Vị trí ứng tuyển: {user_extracted_info.get('Job_Position', 'Không rõ')}\n" \
                           f"Kỹ năng: {', '.join(user_skills_list) if user_skills_list else 'Không có'}\n" \
                           f"Kinh nghiệm: {experience_str if experience_str else 'Không có'}\n" \
                           f"Học vấn: {education_str if education_str else 'Không có'}"

    compare_prompt = f"""
    Bạn là chuyên gia nhân sự. Dưới đây là thông tin CV của một ứng viên và vị trí công việc mục tiêu.
    Hãy phân tích và so sánh kỹ năng, kinh nghiệm của ứng viên với yêu cầu thông thường của vị trí '{target_job_position}'.

    **Thông tin ứng viên:**
    {user_profile_summary}

    **Yêu cầu:**
    1.  Liệt kê các kỹ năng/kinh nghiệm mà ứng viên còn thiếu so với vị trí '{target_job_position}' (missing_in_user_cv).
    2.  Liệt kê các kỹ năng/kinh nghiệm mà ứng viên có nhưng không liên quan trực tiếp hoặc là điểm cộng đặc biệt cho vị trí này (extra_in_user_cv).
    3.  Đưa ra một nhận xét tổng quan ngắn gọn về sự phù hợp của ứng viên với vị trí này (summary).

    Trả về kết quả bằng tiếng Việt, định dạng JSON với các trường: "missing_in_user_cv" (array of strings), "extra_in_user_cv" (array of strings), "summary" (string).
    Chỉ trả về JSON, không markdown, không chú thích, không giải thích thêm.
    """
    raw_json = _call_gemini_model(compare_prompt, api_key, temperature=0.2, response_mime_type="application/json")

    # Clean and parse JSON
    raw_json = re.sub(r"^```json[\r\n]*", "", raw_json)
    raw_json = re.sub(r"^```[\r\n]*", "", raw_json)
    raw_json = re.sub(r"```[\r\n]*$", "", raw_json)
    raw_json = raw_json.strip()

    try:
        return json.loads(raw_json)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_json, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return {"error": "Không parse được JSON từ Gemini", "raw_response": raw_json}
        return {"error": "Không parse được JSON từ Gemini", "raw_response": raw_json}


def suggest_learning_path(missing_skills: List[str], api_key: str, model_name="gemini-1.5-flash") -> str:
    """
    Suggests a learning path based on missing skills using Gemini.
    """
    if not missing_skills or not isinstance(missing_skills, list):
        return ""

    prompt = f"""
Bạn là chuyên gia đào tạo. Dưới đây là danh sách kỹ năng còn thiếu của ứng viên: {', '.join(missing_skills)}.

Hãy đề xuất lộ trình học tập trong 3-6 tháng để giúp người mới cải thiện các kỹ năng này. 
- Chia lộ trình theo từng tháng hoặc từng giai đoạn.
- Nêu rõ mục tiêu, hoạt động hoặc tài liệu nên học cho từng kỹ năng.
- Viết ngắn gọn, rõ ràng, trình bày bằng tiếng Việt, không sử dụng markdown, không dùng ký hiệu đặc biệt, chỉ cần văn bản thuần túy.
"""
    return _call_gemini_model(prompt, api_key, model_name=model_name, temperature=0.7)


def link_callback(uri, rel):
    """
    Hàm trợ giúp để chuyển đổi các đường dẫn tương đối trong HTML (như link tới font, ảnh)
    thành đường dẫn tuyệt đối trên hệ thống để xhtml2pdf có thể tìm thấy.
    """
    # Lấy đường dẫn thư mục gốc của file script hiện tại (ai_model.py)
    base_dir = Path(__file__).resolve().parent
    # Kết hợp đường dẫn gốc với URI từ HTML
    path = os.path.join(base_dir, uri)

    # Kiểm tra xem file có thực sự tồn tại không
    if not os.path.isfile(path):
        return None
    return path


# def clean_text_for_fpdf(text: Any) -> str:
#     """
#     Chuyển đổi bất kỳ kiểu dữ liệu nào sang string và loại bỏ các ký tự
#     có thể gây lỗi cho FPDF, chỉ giữ lại các ký tự in được.
#     """
#     if not isinstance(text, str):
#         text = str(text)
#     # Regex này loại bỏ các ký tự điều khiển và các ký tự không xác định
#     # nhưng vẫn giữ lại hầu hết các ký tự Unicode (bao gồm tiếng Việt).
#     return re.sub(r'[\x00-\x1F\x7F-\x9F]', '', text)
#
#
# def generate_cv_pdf(cv_info: Dict[str, Any], filename: Optional[str] = None) -> str:
#     """
#     Tạo file PDF CV. Phiên bản cuối cùng với xử lý chi tiết cho từng mục
#     và làm sạch dữ liệu triệt để.
#     """
#     folder = "generated_cv_pdf_folder"
#     os.makedirs(folder, exist_ok=True)
#     if not filename:
#         filename = f"cv_{int(time.time())}.pdf"
#     filepath = os.path.join(folder, filename)
#
#     pdf = FPDF()
#     pdf.add_page()
#
#     # --- Cấu hình Font ---
#     try:
#         font_regular_path = r'font/Roboto-Regular.ttf'
#         font_bold_path = r'font/Roboto-Bold.ttf'
#         pdf.add_font('Roboto', '', font_regular_path, uni=True)
#         pdf.add_font('Roboto', 'B', font_bold_path, uni=True)
#     except RuntimeError as e:
#         print(f"LỖI FONT: {e}", file=sys.stderr)
#         return ""
#
#     # --- Tiêu đề CV ---
#     if cv_info.get("Name"):
#         pdf.set_font('Roboto', 'B', 24)
#         pdf.cell(0, 10, clean_text_for_fpdf(cv_info["Name"]).upper(), ln=True, align='C')
#     if cv_info.get("Job_Position"):
#         pdf.set_font('Roboto', '', 16)
#         pdf.cell(0, 10, clean_text_for_fpdf(cv_info["Job_Position"]), ln=True, align='C')
#
#     contact_info = " | ".join(filter(None, [cv_info.get("Email"), cv_info.get("Phone")]))
#     if contact_info:
#         pdf.set_font('Roboto', '', 11)
#         pdf.cell(0, 8, clean_text_for_fpdf(contact_info), ln=True, align='C')
#     pdf.ln(10)
#
#     # --- Cấu trúc và Tiêu đề CV ---
#     section_order = ["Summary", "Skills", "Experience", "Education", "Projects", "Certification"]
#     display_titles = {
#         "Summary": "Tóm Tắt Bản Thân", "Skills": "Kỹ Năng", "Experience": "Kinh Nghiệm Làm Việc",
#         "Education": "Học Vấn", "Projects": "Dự Án", "Certification": "Chứng Chỉ",
#     }
#
#     # --- HÀM GHI CÁC MỤC (Đã được khôi phục logic chi tiết) ---
#     def write_section(title: str, content: Any):
#         if not content: return
#
#         pdf.set_font("Roboto", 'B', 14)
#         pdf.cell(0, 10, title.upper(), ln=True, border='B')
#         pdf.ln(4)
#
#         pdf.set_font("Roboto", '', 11)
#
#         # ===> KHÔI PHỤC LOGIC XỬ LÝ CHI TIẾT <===
#         if isinstance(content, list):
#             for item in content:
#                 if isinstance(item, dict):
#                     # Xử lý Experience
#                     if "position" in item and "company" in item:
#                         pdf.set_font("Roboto", 'B', 12)
#                         pdf.multi_cell(0, 6,
#                                        clean_text_for_fpdf(f"{item.get('position', '')} - {item.get('company', '')}"))
#                         pdf.set_font("Roboto", '', 10)
#                         pdf.ln(6)
#                         pdf.multi_cell(0, 6, clean_text_for_fpdf(f"Thời gian: {item.get('time', '')}"))
#                         pdf.set_font("Roboto", '', 11)
#                         pdf.ln(6)
#                         pdf.multi_cell(0, 6, clean_text_for_fpdf(f"Mô tả: {item.get('description', '')}"))
#                         pdf.ln(4)
#                     # Xử lý Education
#                     elif "school" in item:
#                         pdf.set_font("Roboto", 'B', 12)
#                         pdf.ln(6)
#                         pdf.multi_cell(0, 6, clean_text_for_fpdf(item.get('school', '')))
#                         pdf.set_font("Roboto", '', 11)
#                         pdf.ln(6)
#                         pdf.multi_cell(0, 6, clean_text_for_fpdf(
#                             f"Chuyên ngành: {item.get('major', '')} ({item.get('degree', '')})"))
#                         pdf.ln(6)
#                         pdf.multi_cell(0, 6, clean_text_for_fpdf(f"Năm: {item.get('year', '')}"))
#                         pdf.ln(4)
#                     # Xử lý Projects
#                     elif "name" in item:
#                         pdf.set_font("Roboto", 'B', 12)
#                         pdf.multi_cell(0, 6, clean_text_for_fpdf(item.get('name', '')))
#                         pdf.set_font("Roboto", '', 11)
#                         pdf.ln(6)
#                         pdf.multi_cell(0, 6, clean_text_for_fpdf(f"Vai trò: {item.get('role', '')}"))
#                         pdf.ln(6)
#                         pdf.multi_cell(0, 6, clean_text_for_fpdf(f"Mô tả: {item.get('description', '')}"))
#                         pdf.ln(4)
#                 else:  # Xử lý list of strings (Skills, Certification)
#                     pdf.ln(6)
#                     pdf.multi_cell(0, 6, clean_text_for_fpdf(f"• {item}"))
#         else:  # Xử lý string (Summary)
#             pdf.multi_cell(0, 6, clean_text_for_fpdf(content))
#
#         pdf.ln(5)
#
#     # --- VÒNG LẶP CHÍNH ---
#     for key in section_order:
#         if key in cv_info and cv_info[key]:
#             title = display_titles.get(key, key)
#             content = cv_info[key]
#             write_section(title, content)
#
#     try:
#         pdf.output(filepath)
#         print(f"File PDF đã được lưu tại: {filepath}")
#         return filename
#     except FPDFException as e:
#         print(f"LỖI CUỐI CÙNG KHI GHI FILE PDF: {e}", file=sys.stderr)
#         raise





# def generate_cv_pdf(cv_info: Dict[str, Any], filename: Optional[str] = None) -> str:
#     """
#     Tạo file PDF từ template HTML bằng WeasyPrint và Jinja2.
#     """
#     # 1. Thiết lập đường dẫn
#     base_dir = Path(__file__).resolve().parent
#     output_folder = base_dir / "generated_cv_pdf_folder"
#     output_folder.mkdir(exist_ok=True)  # Tạo thư mục nếu chưa có
#
#     if not filename:
#         filename = f"cv_{int(time.time())}.pdf"
#     filepath = output_folder / filename
#
#     # 2. Cấu hình Jinja2 để nạp template từ thư mục 'templates'
#     template_loader = jinja2.FileSystemLoader(searchpath=str(base_dir / "templates"))
#     template_env = jinja2.Environment(loader=template_loader)
#     template = template_env.get_template("template.html")
#
#     # 3. Đổ dữ liệu vào template
#     rendered_html = template.render(cv=cv_info)
#
#     # 4. Render HTML thành PDF
#     # base_url giúp WeasyPrint tìm được các file liên quan như font, ảnh
#     html_obj = HTML(string=rendered_html, base_url=str(base_dir))
#     html_obj.write_pdf(filepath)
#
#     print(f"File PDF đã được tạo bằng WeasyPrint tại: {filepath}")
#     return str(filename)
VALID_TEMPLATES: List[str] = ["template.html", "template2.html", "template3.html","template4.html", "template5.html", "template6.html"]

def generate_cv_pdf(cv_info: Dict[str, Any], template_name: str = "template.html",
                    filename: Optional[str] = None) -> str:
    """
    Tạo file PDF từ template HTML bằng WeasyPrint và Jinja2.

    Args:
        cv_info (Dict[str, Any]): Dictionary chứa thông tin CV.
        template_name (str): Tên file template trong thư mục 'templates'.
                             Mặc định là 'template.html'.
        filename (Optional[str]): Tên file PDF đầu ra. Nếu không có sẽ tự tạo.

    Returns:
        str: Tên file PDF đã được tạo.

    Raises:
        ValueError: Nếu template_name không hợp lệ.
    """
    # 0. Kiểm tra xem template được chọn có hợp lệ không
    if template_name not in VALID_TEMPLATES:
        raise ValueError(
            f"Template không hợp lệ: '{template_name}'. Vui lòng chọn một trong các template sau: {VALID_TEMPLATES}")

    # 1. Thiết lập đường dẫn
    base_dir = Path(__file__).resolve().parent
    output_folder = base_dir / "generated_cv_pdf_folder"
    output_folder.mkdir(exist_ok=True)  # Tạo thư mục nếu chưa có

    if not filename:
        # Thêm tên template vào filename để dễ phân biệt
        template_prefix = Path(template_name).stem
        filename = f"cv_{template_prefix}_{int(time.time())}.pdf"
    filepath = output_folder / filename

    # 2. Cấu hình Jinja2 để nạp template từ thư mục 'templates'
    template_loader = jinja2.FileSystemLoader(searchpath=str(base_dir / "templates"))
    template_env = jinja2.Environment(loader=template_loader)

    # === THAY ĐỔI CHÍNH: Lấy template dựa trên tham số `template_name` ===
    template = template_env.get_template(template_name)

    # 3. Đổ dữ liệu vào template
    rendered_html = template.render(cv=cv_info)

    # 4. Render HTML thành PDF
    # base_url giúp WeasyPrint tìm được các file liên quan như font, ảnh
    html_obj = HTML(string=rendered_html, base_url=str(base_dir))
    html_obj.write_pdf(filepath)

    print(f"File PDF đã được tạo từ '{template_name}' tại: {filepath}")
    return str(filename)