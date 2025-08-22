# main.py
import asyncio
import platform
import os
import json
import uuid
import shutil
import traceback
import sys
import pathlib
import tempfile
import subprocess
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from typing import List, Optional, Any, Dict
from sqlalchemy.orm import Session
from fastapi import Depends, status
from fastapi.security import OAuth2PasswordRequestForm
import auth, crud, schemas
import models
import database
import google.generativeai as genai
from dotenv import load_dotenv
import ai_model
from fastapi.responses import JSONResponse, FileResponse
from urllib.parse import quote

# Tích hợp module đọc file
from file_parser import extract_text



# Cấu hình ban đầu
load_dotenv()

# Configure Gemini API
api_keys_str = os.environ.get("GEMINI_API_KEYS")
if not api_keys_str:
    raise ValueError("Biến môi trường 'GEMINI_API_KEYS' chưa được thiết lập.")

GEMINI_API_KEYS = [key.strip() for key in api_keys_str.split(',')]

# Load tags config
TAGS_FILE = "tags.json"
LOADED_TAGS = None

def load_tags_from_file():
    global LOADED_TAGS
    try:
        with open(TAGS_FILE, "r", encoding="utf-8") as f:
            LOADED_TAGS = json.load(f)
        print(f"Đã tải thành công tags từ {TAGS_FILE}")
    except Exception as e:
        print(f"Lỗi nghiêm trọng khi tải {TAGS_FILE}: {e}")
        raise


load_tags_from_file()

# --- CẬP NHẬT LOGIC TẢI BÀI TẬP ---
PROBLEMS_FILE = "problems.json"
LOADED_ALL_PROBLEMS = []


def load_and_merge_all_problems():
    """
    Tải và chuẩn hóa dữ liệu từ tất cả các nguồn.
    """
    global LOADED_ALL_PROBLEMS
    all_problems = []

    # 1. Tải các bài tập Backend từ problems.json
    try:
        with open(PROBLEMS_FILE, "r", encoding="utf-8") as f:
            general_problems = json.load(f)
            for prob in general_problems:
                # Đảm bảo các trường cần thiết tồn tại
                prob['is_frontend'] = False
                if 'title' not in prob and 'name' in prob:
                    prob['title'] = prob['name']
            all_problems.extend(general_problems)
        print(f"Đã tải thành công {len(general_problems)} bài tập chung từ {PROBLEMS_FILE}")
    except Exception as e:
        print(f"Lỗi khi tải {PROBLEMS_FILE}: {e}")

    # 2. Tải và chuẩn hóa các bài tập Frontend từ DB
    try:
        frontend_exercises = database.get_all_exercises()  # Hàm này trả về List[Exercise]
        standardized_fe_problems = []
        for ex_obj in frontend_exercises:
            # SỬA LỖI: Chuyển đổi đối tượng Pydantic thành dict một cách an toàn
            ex_dict = ex_obj.model_dump()

            # Tạo một dict chuẩn hóa, đảm bảo có 'title'
            # (model Exercise đã yêu cầu 'title', nên ex_dict chắc chắn có)
            standardized_prob = {
                "id": ex_dict.get("id"),
                "title": ex_dict.get("title"),
                "name": ex_dict.get("title"),  # Dùng title cho cả name để nhất quán
                "description": ex_dict.get("description"),
                "level": ex_dict.get("level"),
                "is_frontend": True,
                "exercise_type": "frontend",
                "group": {"name": "Bài tập Frontend"},
                "sub_group": None,
                # Giữ cả hai key testcases để tương thích
                "testcases": ex_dict.get("frontend_testcases", []),
                "frontend_testcases": ex_dict.get("frontend_testcases", []),
                "backend_testcases": []
            }
            standardized_fe_problems.append(standardized_prob)

        all_problems.extend(standardized_fe_problems)
        print(f"Đã tải và chuẩn hóa thành công {len(frontend_exercises)} bài tập Frontend từ DB")
    except Exception as e:
        print(f"Lỗi khi tải hoặc chuẩn hóa bài tập Frontend: {e}")

    LOADED_ALL_PROBLEMS = all_problems
    print(f"Tổng số bài tập đã gộp: {len(LOADED_ALL_PROBLEMS)}")



# Chạy hàm tải dữ liệu khi khởi động
load_and_merge_all_problems()

# Khởi tạo ứng dụng FastAPI
app = FastAPI(
    title="Hệ thống Phân Tích CV & Gợi Ý Bài Tập",
    description="API nhận file CV (pdf, docx, txt), trích xuất thông tin, đưa ra nhận xét và gợi ý bài tập.",
    version="6.2.0"  # Cập nhật phiên bản
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

PDF_OUTPUT_FOLDER = "generated_cv_pdf_folder"

os.makedirs(PDF_OUTPUT_FOLDER, exist_ok=True)


# --- Pydantic Models (Cập nhật) ---
class SkillProficiency(BaseModel):
    ky_nang: str = Field(..., description="Tên kỹ năng, công nghệ.")
    trinh_do_uoc_tinh: str = Field(..., description="Trình độ ước tính (ví dụ: Cơ bản, Thành thạo, Chuyên sâu).")


# --- Pydantic Models ---
class ExtractedCVInfo(BaseModel):
    vi_tri_ung_tuyen: Optional[str] = Field(None, description="Vị trí ứng tuyển trích xuất từ CV.")
    chuyen_nganh: Optional[str] = Field(None, description="Chuyên ngành học trích xuất từ CV.")
    so_nam_kinh_nghiem_tong_quan: Optional[str] = Field(None, description="Ước lượng tổng số năm kinh nghiệm.")
    ngon_ngu_the_manh: Optional[str] = Field(None, description="Ngôn ngữ lập trình thế mạnh trích xuất từ CV.")
    ky_nang_cong_nghe_khac: Optional[List[str]] = Field(default_factory=list,
                                                        description="Danh sách các kỹ năng công nghệ khác.")
    cong_cu_cv: Optional[List[str]] = Field(default_factory=list, description="Các công cụ phát triển, quản lý dự án.")
    ky_nang_mem_cv: Optional[List[str]] = Field(default_factory=list, description="Danh sách các kỹ năng mềm.")
    phuong_phap_lam_viec_cv: Optional[List[str]] = Field(default_factory=list,
                                                         description="Các phương pháp làm việc hoặc quy trình.")
    linh_vuc_kinh_nghiem_cv: Optional[List[str]] = Field(default_factory=list,
                                                         description="Các lĩnh vực, ngành nghề ứng dụng đã có kinh nghiệm.")
    chung_chi_cv: Optional[List[str]] = Field(default_factory=list, description="Danh sách các chứng chỉ.")
    trinh_do_ngoai_ngu_cv: Optional[List[str]] = Field(default_factory=list, description="Mô tả về trình độ ngoại ngữ.")


class MatchedInfo(BaseModel):
    dang_bai_tap_goi_y: List[str] = Field(..., description="Danh sách các dạng bài tập được Gemini gợi ý.")
    ngon_ngu_goi_y: str = Field(..., description="Ngôn ngữ lập trình được Gemini gợi ý.")
    level_goi_y: int = Field(..., ge=1, le=5, description="Mức độ khó của bài tập (1-5) được Gemini gợi ý.")
    nhan_xet_tong_quan: Optional[str] = Field(None, description="Đoạn nhận xét chi tiết về hồ sơ ứng viên.")
    extracted_cv_info: ExtractedCVInfo = Field(..., description="Thông tin chi tiết đã được trích xuất từ CV.")


class SuggestedProblemsResponse(MatchedInfo):
    suggested_problems: List[dict] = Field(..., description="Danh sách các bài tập được gợi ý.")
    suggested_problems_count: int = Field(..., description="Số lượng bài tập được gợi ý.")


# --- Pydantic Models for User & Auth ---
class UserCreate(BaseModel):
    username: str
    email: str
    password: str


class UserPublic(BaseModel):
    username: str
    email: str

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str

class GenerateCVRequest(BaseModel):
    cv_data: schemas.DetailedExtractedCVInfo = Field(..., description="Đối tượng chứa thông tin chi tiết của CV đã được trích xuất.")
    template_name: str = Field(..., description="Tên file template người dùng đã chọn (ví dụ: 'template2.html').")



# --- Hàm xây dựng Prompt ---
# Cập nhật để nhận DetailedExtractedCVInfo
def build_matching_prompt(extracted_info: schemas.DetailedExtractedCVInfo) -> str:
    """
    Xây dựng prompt để đưa ra nhận xét sâu sắc và gợi ý bài tập phù hợp,
    sử dụng DetailedExtractedCVInfo.
    """
    level_mapping_guide_str = "\n".join(
        [f"  - Level {k}: {v}" for k, v in LOADED_TAGS.get("level", {}).get("mapping_guide", {}).items()]
    )

    # Lấy thông tin từ DetailedExtractedCVInfo
    job_position = extracted_info.Job_Position or 'chưa xác định'
    skills = ', '.join(extracted_info.Skills) if extracted_info.Skills else 'không có'
    summary = extracted_info.Summary or 'chưa rõ'

    # Tạo một bản tóm tắt hồ sơ dạng văn xuôi để AI dễ "cảm" hơn
    profile_narrative = (
        f"Đây là hồ sơ của một ứng viên cho vị trí '{job_position}'. "
        f"Ứng viên có các kỹ năng: {skills}. "
        f"Tóm tắt bản thân: '{summary}'."
        # Bạn có thể thêm các trường khác từ detailed_cv_info nếu muốn AI phân tích sâu hơn
        # Ví dụ: "Kinh nghiệm làm việc: {', '.join([exp.description for exp in extracted_info.Experience]) if extracted_info.Experience else 'không có'}."
    )

    prompt = f"""
    Bạn là một Giám đốc Kỹ thuật (Engineering Director) dày dạn kinh nghiệm, đang đánh giá hồ sơ của một ứng viên tiềm năng để đưa ra lộ trình phát triển.
    Nhiệm vụ của bạn là cung cấp một bản phân tích và gợi ý chi tiết, mang tính xây dựng cao dựa trên hồ sơ đã được tóm tắt.

    **HỒ SƠ ỨNG VIÊN:**
    {profile_narrative}

    **HƯỚNG DẪN ĐÁNH GIÁ LEVEL (Từ 1-5):**
    {level_mapping_guide_str}

    **YÊU CẦU ĐẦU RA (Định dạng JSON):**
    Hãy suy nghĩ từng bước và điền vào các trường sau:

    1.  **"level_goi_y" (integer):** Dựa vào kinh nghiệm, độ phức tạp của công nghệ và dự án trong hồ sơ, hãy chọn MỘT level (1-5) phù hợp nhất với ứng viên theo hướng dẫn ở trên.

    2.  **"ngon_ngu_goi_y" (string):** Chọn MỘT ngôn ngữ lập trình phù hợp nhất để ứng viên tập trung. Thông thường là ngôn ngữ thế mạnh của họ, trừ khi hồ sơ cho thấy họ đang muốn chuyển hướng.

    3.  **"dang_bai_tap_goi_y" (array of strings):** Dựa trên level và các kỹ năng của ứng viên, hãy gợi ý 3-5 dạng bài tập giúp họ cải thiện.
        - *Ví dụ suy luận:* Nếu ứng viên mạnh ReactJS (level 3) nhưng yếu về quản lý state, gợi ý "Bài tập với Redux/Context API". Nếu mạnh Java nhưng chưa làm nhiều về database, gợi ý "Dự án nhỏ với Spring Data JPA".

    4.  **"nhan_xet_tong_quan" (string):** Viết một đoạn nhận xét chuyên sâu theo cấu trúc SWOT-like (khoảng 100-150 từ).
        - **Điểm mạnh (Strengths):** Nêu 2 điểm mạnh kỹ thuật rõ ràng nhất (ví dụ: "Thành thạo ReactJS và Next.js thể hiện qua dự án X", "Nền tảng C++ vững chắc").
        - **Điểm yếu/Cần cải thiện (Weaknesses):** Chỉ ra 1-2 điểm mà hồ sơ còn thiếu hoặc yếu (ví dụ: "Kinh nghiệm làm việc với cơ sở dữ liệu quan hệ còn hạn chế", "Chưa thể hiện kinh nghiệm về kiểm thử tự động (Unit Test)").
        - **Cơ hội (Opportunities):** Gợi ý 1-2 hướng phát triển cụ thể để ứng viên tiến lên level tiếp theo (ví dụ: "Để từ level 3 lên 4, nên tập trung vào việc thiết kế và triển khai các RESTful API hoàn chỉnh", "Nên tìm hiểu sâu hơn về Docker và CI/CD để nâng cao kỹ năng DevOps").

    **QUY TẮC ĐẦU RA:**
    - Chỉ trả về một đối tượng JSON duy nhất.
    - Không chứa bất kỳ lời giải thích hay định dạng markdown nào.
    """
    return prompt.strip()


# --- Hàm gọi Gemini API ---
async def call_gemini_api(prompt_text: str, temperature: float, context: str = "chung") -> dict:
    print(f"\n--- Gửi Prompt tới Gemini ({context}) với Temperature: {temperature} ---")

    for api_key in GEMINI_API_KEYS:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name="gemini-1.5-flash-latest")
            safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
            generation_config = genai.types.GenerationConfig(temperature=temperature, response_mime_type="application/json")
            response = await model.generate_content_async(prompt_text, generation_config=generation_config,
                                                          safety_settings=safety_settings)

            if not response.parts:
                print(f"Lỗi: Gemini không trả về nội dung hợp lệ với key {api_key}. Thử key tiếp theo.")
                continue

            raw_text_response = response.text.strip()
            if not raw_text_response:
                print(f"Lỗi: Dữ liệu từ Gemini sau khi làm sạch là rỗng với key {api_key}. Thử key tiếp theo.")
                continue

            try:
                return json.loads(raw_text_response)
            except json.JSONDecodeError as e:
                print(f"Lỗi: Lỗi phân tích JSON từ Gemini với key {api_key}. Thử key tiếp theo.")
                continue

        except Exception as e:
            print(f"Lỗi: Lỗi hệ thống khi xử lý với Gemini bằng key {api_key}: {str(e)}. Thử key tiếp theo.")
            continue

    raise HTTPException(status_code=500, detail=f"Tất cả các API key của Gemini đều đã thất bại ({context}).")


# --- HÀM HỖ TRỢ ---
# Cập nhật để nhận DetailedExtractedCVInfo
def is_frontend_profile(extracted_info: schemas.DetailedExtractedCVInfo) -> bool:
    """
    Kiểm tra xem hồ sơ có thiên về Frontend hoặc Fullstack hay không,
    sử dụng DetailedExtractedCVInfo.
    """
    position_keywords = {"frontend", "front-end", "ui/ux", "ui-ux", "web developer", "web designer", "fullstack",
                         "full-stack"}
    tech_keywords = {"react", "vue", "angular", "next.js", "svelte", "javascript", "typescript", "html", "css", "scss",
                     "tailwind"}

    # Kiểm tra vị trí ứng tuyển
    position = (extracted_info.Job_Position or "").lower().strip()
    if any(keyword in position for keyword in position_keywords):
        return True

    # Tổng hợp tất cả các kỹ năng từ trường "Skills"
    all_skills_lower = {skill.lower() for skill in extracted_info.Skills}

    # Kiểm tra xem có kỹ năng frontend nào trong danh sách không
    if not tech_keywords.isdisjoint(all_skills_lower):
        return True

    return False


# --- Khởi tạo tài khoản Admin mặc định ---

@app.on_event("startup")
async def create_initial_admin():
    database.Base.metadata.create_all(bind=database.engine)
    db = next(database.get_db())  # Lấy một phiên DB
    try:
        # Kiểm tra xem có tài khoản admin nào tồn tại không
        admin_user = crud.get_admin_user(db)
        if not admin_user:
            print("Không tìm thấy tài khoản admin. Đang tạo tài khoản admin mặc định...")
            admin_username = os.getenv("ADMIN_USERNAME", "admin")
            admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")
            admin_password = os.getenv("ADMIN_PASSWORD", "adminpassword")  # Thay đổi mật khẩu mặc định này

            # Tạo đối tượng UserCreate với vai trò ADMIN
            admin_user_data = schemas.AdminUserCreate(  # Use AdminUserCreate schema
                username=admin_username,
                email=admin_email,
                password=admin_password,
                role=models.Role.ADMIN  # Gán vai trò ADMIN
            )
            hashed_password = auth.get_password_hash(admin_user_data.password)
            crud.create_user(db, user=admin_user_data, hashed_password=hashed_password)
            print(f"Đã tạo tài khoản admin: {admin_username} với email: {admin_email}")
            print(f"Mật khẩu mặc định (nên thay đổi): {admin_password}")
        else:
            print("Tài khoản admin đã tồn tại.")
    except Exception as e:
        print(f"Lỗi khi tạo tài khoản admin mặc định: {e}")
    finally:
        db.close()


# --- API ENDPOINTS ---

@app.post("/token", response_model=schemas.Token, tags=["Authentication"])
async def login_for_access_token(
        form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)
):
    user = auth.authenticate_user(db, username=form_data.username, password=form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    access_token = auth.create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}



@app.get("/users/me", response_model=schemas.UserPublic, tags=["Authentication"])
async def read_users_me(current_user: models.User = Depends(auth.get_current_active_user)):
    # API này có thể truy cập bởi tất cả các vai trò đã đăng nhập
    return current_user

@app.get("/admin/users/all", response_model=List[schemas.UserPublic], tags=["Admin - User Management"])
def read_all_users(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.role_required([models.Role.ADMIN]))
):
    users = crud.get_users(db)
    return users


@app.put("/admin/users/{user_id}", response_model=schemas.UserPublic, tags=["Admin - User Management"])
def update_user_by_admin(
        user_id: int,
        user_update: schemas.UserUpdate,
        db: Session = Depends(database.get_db),
        current_user: models.User = Depends(auth.role_required([models.Role.ADMIN]))
):
    """
    Cập nhật thông tin người dùng (email, password, role) theo ID.
    Chỉ dành cho Admin.
    """
    # Lấy thông tin người dùng cần cập nhật từ DB
    db_user = crud.get_user(db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # === PHẦN CHỈNH SỬA LOGIC KIỂM TRA EMAIL ===
    # Chỉ kiểm tra email nếu nó được cung cấp trong request body
    if user_update.email:
        # Tìm xem có người dùng nào khác đã sử dụng email này chưa
        existing_user = crud.get_user_by_email(db, email=user_update.email)
        # Nếu tồn tại người dùng có email đó VÀ ID của họ khác với ID người dùng đang cập nhật
        # thì mới báo lỗi. Điều này cho phép giữ nguyên email cũ mà không bị lỗi.
        if existing_user and existing_user.id != user_id:
            raise HTTPException(status_code=400, detail="Email is already registered by another user")
    # === KẾT THÚC PHẦN CHỈNH SỬA ===

    # Gọi hàm CRUD để thực hiện cập nhật trong database
    updated_user = crud.update_user(db=db, user_id=user_id, user_update=user_update)

    # Trả về thông tin người dùng đã được cập nhật
    return updated_user

# New API for Admin to create a single user
@app.post("/admin/users/create", response_model=schemas.UserPublic, tags=["Admin - User Management"])
def create_user_by_admin(
        user: schemas.AdminUserCreate,  # Use AdminUserCreate schema
        db: Session = Depends(database.get_db),
        current_user: models.User = Depends(auth.role_required([models.Role.ADMIN]))  # Only Admin can access
):
    if crud.get_user_by_username(db, username=user.username):
        raise HTTPException(status_code=400, detail="Username already registered")
    if crud.get_user_by_email(db, email=user.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = auth.get_password_hash(user.password)
    db_user = crud.create_user(db=db, user=user, hashed_password=hashed_password)
    return db_user


# New API for Admin to create multiple users (batch)
@app.post("/admin/users/batch-create", tags=["Admin - User Management"])
def batch_create_users_by_admin(
        batch_request: schemas.BatchUserCreateRequest,
        db: Session = Depends(database.get_db),
        current_user: models.User = Depends(auth.role_required([models.Role.ADMIN]))
):
    results = []
    for user_data in batch_request.users:
        username = user_data.username
        email = user_data.email
        password = batch_request.default_password
        role = batch_request.default_role

        if crud.get_user_by_username(db, username=username):
            results.append(
                {"username": username, "email": email, "status": "failed", "detail": "Username already registered"})
            continue
        if crud.get_user_by_email(db, email=email):
            results.append(
                {"username": email, "email": email, "status": "failed", "detail": "Email already registered"})
            continue

        hashed_password = auth.get_password_hash(password)
        try:
            # Create an AdminUserCreate object for crud.create_user
            temp_user_create = schemas.AdminUserCreate(  # Changed from schemas.UserCreate
                username=username,
                email=email,
                password=password,  # This password will be hashed by crud.create_user
                role=role  # Use the default_role from batch_request
            )
            db_user = crud.create_user(db=db, user=temp_user_create, hashed_password=hashed_password)
            results.append(
                {"username": db_user.username, "email": db_user.email, "status": "success", "role": db_user.role})
        except Exception as e:
            db.rollback()  # Rollback if any user creation fails in batch
            results.append({"username": username, "email": email, "status": "failed", "detail": str(e)})

    db.commit()  # Commit changes after all users are processed in the batch
    return {"message": "Batch user creation process completed.", "results": results}


@app.post("/analyze_cv_comprehensive", response_model=schemas.ComprehensiveCVAnalysisResponse,
          summary="Phân tích CV toàn diện: trích xuất, gợi ý VÀ TẠO FILE PDF",
          tags=["Core CV Analysis"],
          dependencies=[Depends(auth.role_required([models.Role.ADMIN, models.Role.LECTURER, models.Role.STUDENT]))])
async def analyze_cv_comprehensive_endpoint(
        file: UploadFile = File(..., description="File CV định dạng .pdf, .docx, hoặc .txt")
):
    # 1. Đọc và trích xuất văn bản từ file
    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = pathlib.Path(temp_dir) / file.filename
        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        finally:
            file.file.close()
        cv_text = extract_text(file_path)

    if not cv_text or not cv_text.strip():
        raise HTTPException(status_code=400, detail="Không thể đọc nội dung từ file hoặc file trống.")

    # 2. Trích xuất thông tin chi tiết và validate
    detailed_cv_info_dict = ai_model.extract_detailed_cv_info(cv_text, GEMINI_API_KEYS)
    try:
        detailed_cv_info_obj = schemas.DetailedExtractedCVInfo(**detailed_cv_info_dict)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=f"Lỗi xác thực dữ liệu CV: {e.errors()}")

    # 3. Chạy song song các tác vụ AI và tạo file để tối ưu thời gian
    target_job_position = detailed_cv_info_obj.Job_Position or "Software Developer"

    comparison_task = asyncio.to_thread(
        ai_model.compare_and_identify_gaps,
        detailed_cv_info_obj.model_dump(), target_job_position, GEMINI_API_KEYS
    )
    matching_prompt = build_matching_prompt(detailed_cv_info_obj)
    suggestions_task = call_gemini_api(matching_prompt, temperature=0.2, context="get_problem_suggestions")
    pdf_generation_task = asyncio.to_thread(
        ai_model.generate_cv_pdf,  # Gọi hàm mới generate_cv_pdf
        cv_info=detailed_cv_info_dict,
    )

    results = await asyncio.gather(
        comparison_task, suggestions_task, pdf_generation_task, return_exceptions=True
    )

    comparison_results, gemini_suggestions_dict, generated_filename = results

    # Kiểm tra lỗi một cách chi tiết hơn
    if isinstance(comparison_results, Exception):
        print("--- LỖI CHI TIẾT KHI SO SÁNH CV ---")
        traceback.print_exception(type(comparison_results), comparison_results, comparison_results.__traceback__)
        raise HTTPException(status_code=500, detail=f"Lỗi so sánh CV: {str(comparison_results)}")

    if isinstance(gemini_suggestions_dict, Exception):
        print("--- LỖI CHI TIẾT KHI GỢI Ý BÀI TẬP ---")
        traceback.print_exception(type(gemini_suggestions_dict), gemini_suggestions_dict,
                                  gemini_suggestions_dict.__traceback__)
        raise HTTPException(status_code=500, detail=f"Lỗi gợi ý bài tập: {str(gemini_suggestions_dict)}")

    if isinstance(generated_filename, Exception):
        # ĐÂY LÀ PHẦN QUAN TRỌNG NHẤT
        print("--- LỖI CHI TIẾT KHI TẠO FILE PDF ---")
        # In toàn bộ traceback ra console của server
        traceback.print_exception(type(generated_filename), generated_filename, generated_filename.__traceback__)
        print("------------------------------------")
        # Trả về thông báo lỗi chi tiết cho frontend
        raise HTTPException(status_code=500, detail=f"Lỗi tạo file PDF: {str(generated_filename)}")
    # 4. Xử lý kết quả từ các tác vụ đã chạy
    missing_skills = comparison_results.get("missing_in_user_cv", [])
    learning_path_task = asyncio.to_thread(ai_model.suggest_learning_path, missing_skills,
                                           GEMINI_API_KEYS) if missing_skills else asyncio.sleep(0, result="")

    suggested_level = gemini_suggestions_dict.get("level_goi_y")
    final_problems = [p for p in LOADED_ALL_PROBLEMS if p.get("level") == suggested_level and not p.get("is_frontend")]
    if is_frontend_profile(detailed_cv_info_obj):
        final_problems.extend([p for p in LOADED_ALL_PROBLEMS if p.get("is_frontend")])
    unique_problems = list({p['id']: p for p in final_problems}.values())

    learning_path = await learning_path_task

    # 5. Đóng gói và trả về phản hồi toàn diện
    response_payload = {
        "detailed_cv_info": detailed_cv_info_obj.model_dump(),
        "missing_skills": missing_skills,
        "extra_skills": comparison_results.get("extra_in_user_cv", []),
        "overall_summary": comparison_results.get("summary", ""),
        "learning_path": learning_path,
        "suggested_problems": unique_problems,
        "suggested_problems_count": len(unique_problems),
        "suggested_level": suggested_level,
        "suggested_language": gemini_suggestions_dict.get("ngon_ngu_goi_y"),
        "generated_cv_pdf": generated_filename
    }

    return schemas.ComprehensiveCVAnalysisResponse(**response_payload)


@app.get("/download-cv/{filename}", tags=["CV Generation"])
async def download_cv_pdf(filename: str):
    directory = "generated_cv_pdf_folder"
    file_path = os.path.join(directory, filename)

    if os.path.exists(file_path):
        # Mã hóa tên file theo chuẩn UTF-8 để trình duyệt hiểu
        encoded_filename = quote(filename)

        return FileResponse(
            path=file_path,
            filename=filename,  # Giữ lại tên file gốc để hiển thị
            media_type='application/pdf',
            # Sửa lại header để tương thích với Unicode
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
            }
        )
    raise HTTPException(status_code=404, detail="Không tìm thấy file.")

@app.get("/exercises/{exercise_id}", summary="Lấy thông tin chi tiết bài tập theo ID từ danh sách tổng hợp",
         dependencies=[Depends(auth.role_required([models.Role.ADMIN, models.Role.LECTURER, models.Role.STUDENT]))])
async def get_exercise_info_by_id_endpoint(
        exercise_id: str = Path(..., description="ID của bài tập cần lấy thông tin")):
    exercise = next((prob for prob in LOADED_ALL_PROBLEMS if str(prob.get('id')) == exercise_id), None)

    if not exercise:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy bài tập với ID: {exercise_id}")

    # Trả về đối tượng dict đã tìm thấy
    return exercise


@app.get("/get_all_problems", summary="Lấy toàn bộ danh sách bài tập",
         dependencies=[Depends(auth.role_required([models.Role.ADMIN, models.Role.LECTURER, models.Role.STUDENT]))])
async def get_all_problems_endpoint():
    return {"count": len(LOADED_ALL_PROBLEMS), "results": LOADED_ALL_PROBLEMS}


@app.get("/get_problems_by_level", summary="Lấy danh sách bài tập lọc theo level",
         dependencies=[Depends(auth.role_required([models.Role.ADMIN, models.Role.LECTURER, models.Role.STUDENT]))])
async def get_problems_by_level_endpoint(
        level: int = Query(..., ge=1, le=5, description="Lọc bài tập theo mức độ khó")):
    filtered = [p for p in LOADED_ALL_PROBLEMS if p.get("level") == level and not p.get("is_frontend")]
    return {"count": len(filtered), "results": filtered}


@app.post("/create-exercise", summary="Tạo bài tập mới",
          dependencies=[Depends(auth.role_required([models.Role.ADMIN, models.Role.LECTURER]))])
def create_exercise_endpoint(exercise: models.Exercise,
                             current_user: models.User = Depends(auth.get_current_active_user)):
    try:
        exercise_id = database.add_exercise(exercise)
        return {"message": "Bài tập đã tạo thành công!", "id": exercise_id, "title": exercise.title}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi server khi tạo bài tập: {str(e)}")


GRADER_FRONTEND_SCRIPT_PATH = pathlib.Path(__file__).parent / "grader" / "judge.py"
GRADER_BACKEND_SCRIPT_PATH = pathlib.Path(__file__).parent / "grader" / "judge_backend.py"


def _run_grader_script_sync(cmd: List[str], env: Optional[dict] = None) -> subprocess.CompletedProcess:
    current_env = os.environ.copy()
    current_env['PYTHONUTF8'] = '1'
    if env:
        current_env.update(env)
    return subprocess.run(cmd, capture_output=True, text=True, check=False, encoding='utf-8', shell=False,
                          env=current_env)


@app.post("/submit-solution", summary="Nộp bài giải và chấm điểm",
          dependencies=[Depends(auth.role_required([models.Role.ADMIN, models.Role.LECTURER, models.Role.STUDENT]))])
async def submit_solution_endpoint(exercise_id: int = Form(...), file: UploadFile = File(...)):
    exercise_dict = next((p for p in LOADED_ALL_PROBLEMS if p.get('id') == exercise_id), None)
    if not exercise_dict:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy bài tập với ID: {exercise_id}")

    try:
        exercise = models.Exercise(**exercise_dict)
    except ValidationError as e:
        raise HTTPException(status_code=500, detail=f"Lỗi dữ liệu bài tập không hợp lệ: {e}")

    user_code_path = None
    results_output_path = None
    results_data = []

    try:
        # Tạo file tạm cho bài nộp của người dùng
        file_suffix = pathlib.Path(file.filename).suffix or ".tmp"
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_suffix, mode="wb") as temp_file:
            content = await file.read()
            temp_file.write(content)
            user_code_path = temp_file.name

        # Logic chọn máy chấm và chuẩn bị tham số
        if exercise.exercise_type == models.ExerciseType.BACKEND:
            script_path = GRADER_BACKEND_SCRIPT_PATH
            if not exercise.backend_testcases:
                raise HTTPException(status_code=400, detail="Bài tập Backend này chưa có test case.")
            test_cases_str = json.dumps([tc.model_dump() for tc in exercise.backend_testcases])
            cmd = [sys.executable, str(script_path.resolve()), user_code_path, test_cases_str]

        elif exercise.exercise_type == models.ExerciseType.FRONTEND:
            script_path = GRADER_FRONTEND_SCRIPT_PATH
            if not (exercise.frontend_testcases or exercise_dict.get("testcases")):
                raise HTTPException(status_code=400, detail="Bài tập Frontend này chưa có test case.")

            # SỬA LỖI: Tạo file tạm cho output của máy chấm frontend
            with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as output_file:
                results_output_path = pathlib.Path(output_file.name)

            exercise_json_str = json.dumps(exercise_dict)
            # SỬA LỖI: Thêm tham số thứ 3 (output_file_path) vào lệnh cmd
            cmd = [sys.executable, str(script_path.resolve()), exercise_json_str, user_code_path,
                   str(results_output_path)]

        else:
            raise HTTPException(status_code=400, detail="Loại bài tập không được hỗ trợ.")

        # Gọi script chấm bài
        loop = asyncio.get_running_loop()
        process_result = await loop.run_in_executor(None, _run_grader_script_sync, cmd)

        print(f"--- GRADER STDOUT ---\n{process_result.stdout}\n---------------------")
        print(f"--- GRADER STDERR ---\n{process_result.stderr}\n---------------------")

        if exercise.exercise_type == models.ExerciseType.BACKEND:
            # Xử lý kết quả cho BACKEND
            if process_result.returncode != 0 and not process_result.stdout:
                raise HTTPException(status_code=500,
                                    detail=f"Script chấm điểm backend thất bại. Lỗi: {process_result.stderr.strip()}")
            try:
                results_data = json.loads(process_result.stdout)
            except json.JSONDecodeError:
                raise HTTPException(status_code=500,
                                    detail=f"Không thể đọc JSON từ stdout của máy chấm backend. Output: {process_result.stdout}")

        elif exercise.exercise_type == models.ExerciseType.FRONTEND:
            # Xử lý kết quả cho FRONTEND
            if not results_output_path or not results_output_path.exists():
                raise HTTPException(status_code=500,
                                    detail=f"Máy chấm frontend không tạo file kết quả. Lỗi: {process_result.stderr.strip()}")
            try:
                with open(results_output_path, 'r', encoding='utf-8') as f:
                    results_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                with open(results_output_path, 'r', encoding='utf-8') as f_err:
                    error_content = f_err.read()
                raise HTTPException(
                    status_code=500,
                    detail=f"Không thể đọc JSON. Nội dung file lỗi: {error_content}"
                )

    finally:
        if user_code_path and os.path.exists(user_code_path):
            os.unlink(user_code_path)
        if results_output_path and os.path.exists(results_output_path):
            os.unlink(results_output_path)

    passed_count = sum(1 for r in results_data if r.get("status") == "ACCEPTED" or (
            isinstance(r, dict) and r.get("result", "").strip() == "✅ Passed"))
    total_tests = len(results_data)

    return {
        "exercise_id": exercise_id,
        "exercise_type": exercise.exercise_type.value,
        "score": f"{passed_count}/{total_tests}",
        "details": results_data
    }

@app.post("/suggest_learning_path", summary="Gợi ý lộ trình học tập dựa trên danh sách kỹ năng",
          dependencies=[Depends(auth.role_required([models.Role.ADMIN, models.Role.LECTURER, models.Role.STUDENT]))])
async def suggest_learning_path_endpoint(request: schemas.LearningPathRequest):
    try:
        learning_path_text = ai_model.suggest_learning_path(request.skills, GEMINI_API_KEYS)
        return {"learning_path": learning_path_text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi tạo lộ trình học tập: {str(e)}")

@app.post("/upload-and-generate-cv",
          summary="Tải CV, trích xuất và tạo file PDF mới từ mẫu HTML",
          tags=["CV Generation"])
async def upload_and_generate_cv_endpoint(
    file: UploadFile = File(..., description="File CV định dạng .pdf, .docx, hoặc .txt")
):
    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = pathlib.Path(temp_dir) / file.filename
        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        finally:
            file.file.close()
        cv_text = extract_text(file_path)

    if not cv_text or not cv_text.strip():
        raise HTTPException(status_code=400, detail="Không thể đọc nội dung từ file hoặc file trống.")

    # 1. Trích xuất thông tin chi tiết từ CV bằng ai_model
    detailed_cv_info_dict = ai_model.extract_detailed_cv_info(cv_text, GEMINI_API_KEYS)
    if detailed_cv_info_dict.get("error"):
        raise HTTPException(status_code=500, detail=f"Lỗi trích xuất CV chi tiết: {detailed_cv_info_dict['error']}")

    # 2. Tạo file PDF từ template HTML
    try:
        # Gọi hàm async mới trong ai_model
        generated_filename = await ai_model.generate_pdf_from_html_template(
            cv_info=detailed_cv_info_dict,
            template_path='templates/template.html'  # Đường dẫn đến template của bạn
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi tạo file PDF từ HTML: {str(e)}")

    # 3. Xây dựng response JSON giống hệt API của đồng nghiệp
    # URL để xem/tải file trực tiếp từ thư mục tĩnh đã mount
    pdf_url = f"/generated_cvs/{generated_filename}"

    # Tạo response cuối cùng
    final_response = {
        "filename": file.filename,
        "analysis": {
            # Bạn có thể thêm các kết quả phân tích khác vào đây nếu muốn
            "extracted_info": detailed_cv_info_dict,
            # Các khóa tương thích với API cũ
            "generated_cv_pdf": generated_filename,
            "generated_cv_pdf_url": pdf_url, # Link để xem
            "generated_cv_pdf_download": pdf_url # Link để tải (frontend sẽ xử lý)
        }
    }

    return JSONResponse(content=final_response)


@app.post("/generate-cv",
          summary="Tạo file CV PDF từ dữ liệu và mẫu template được chọn",
          tags=["CV Generation"],
          dependencies=[Depends(auth.role_required([models.Role.ADMIN, models.Role.LECTURER, models.Role.STUDENT]))])
async def generate_cv_from_template_endpoint(request: GenerateCVRequest):
    """
    Endpoint này nhận dữ liệu CV chi tiết và tên của một template,
    sau đó tạo ra một file CV PDF tương ứng.
    - **cv_data**: Dữ liệu CV đã được trích xuất từ bước phân tích.
    - **template_name**: Tên của file template (ví dụ: 'template.html', 'template2.html').
    """
    try:
        # Dữ liệu cv_data từ request là một Pydantic model, cần chuyển thành dict
        cv_info_dict = request.cv_data.model_dump()

        # Gọi hàm generate_cv_pdf trong một thread riêng để không block server
        # Hàm này đã được sửa ở lần trước để nhận `template_name`
        generated_filename = await asyncio.to_thread(
            ai_model.generate_cv_pdf,
            cv_info=cv_info_dict,
            template_name=request.template_name
        )

        # Trả về tên file đã tạo thành công theo đúng yêu cầu của frontend
        return {"filename": generated_filename}

    except ValueError as ve:
        # Bắt lỗi nếu template_name không hợp lệ (đã thêm trong hàm generate_cv_pdf)
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        # In traceback ra console để debug
        print("--- LỖI CHI TIẾT KHI TẠO FILE PDF TÙY CHỌN ---")
        traceback.print_exc()
        print("---------------------------------------------")
        # Trả về lỗi 500 cho frontend
        raise HTTPException(status_code=500, detail=f"Đã có lỗi xảy ra khi tạo file PDF: {str(e)}")
