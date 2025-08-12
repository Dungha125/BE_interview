# schemas.py

from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Any, Dict

import models
from models import ExerciseType, Role # Import từ models.py

# --- Pydantic Models for User & Auth ---
class UserBase(BaseModel):
    username: str
    email: EmailStr

class AdminUserCreate(UserBase):
    password: str
    role: Role # Admin can specify role

# BatchUserCreateItem: For a single user entry in a batch creation
class BatchUserCreateItem(BaseModel):
    username: str
    email: EmailStr

# BatchUserCreateRequest: For the entire batch creation request
class BatchUserCreateRequest(BaseModel):
    users: List[BatchUserCreateItem]
    default_password: str = Field("ptit@123", description="Mật khẩu mặc định cho các tài khoản được tạo hàng loạt.")
    default_role: Role = Field(Role.STUDENT, description="Vai trò mặc định cho các tài khoản được tạo hàng loạt.")


class UserPublic(UserBase):
    id: int
    is_active: bool
    role: Role
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class LearningPathRequest(BaseModel):
    skills: List[str] = Field(..., description="Danh sách các kỹ năng cần học để tạo lộ trình.")

class EducationEntry(BaseModel):
    school: Optional[str] = None
    major: Optional[str] = None
    degree: Optional[str] = None
    year: Optional[str] = None # Keeping as string as per your data

class ExperienceEntry(BaseModel):
    company: Optional[str] = None
    position: Optional[str] = None
    time: Optional[str] = None
    description: Optional[str] = None

class ProjectEntry(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    role: Optional[str] = None
    technologies: Optional[List[str]] = Field(default_factory=list)


# This reflects the detailed extraction from model.py
class DetailedExtractedCVInfo(BaseModel):
    Name: Optional[str] = None
    Email: Optional[str] = None
    Phone: Optional[str] = None
    Job_Position: Optional[str] = None
    Skills: Optional[List[str]] = Field(default_factory=list)
    # Use the new nested models for these fields
    Education: Optional[List[EducationEntry]] = Field(default_factory=list)
    Experience: Optional[List[ExperienceEntry]] = Field(default_factory=list)
    Certification: Optional[List[str]] = Field(default_factory=list) # Assuming Certification is still list of strings
    Projects: Optional[List[ProjectEntry]] = Field(default_factory=list)
    Summary: Optional[str] = None
    # Add raw_response for debugging if parsing fails in model.py
    error: Optional[str] = None
    raw_response: Optional[str] = None


# New comprehensive response model for CV analysis and suggestions
class ComprehensiveCVAnalysisResponse(BaseModel):
    detailed_cv_info: DetailedExtractedCVInfo = Field(..., description="Thông tin chi tiết được trích xuất từ CV.")
    missing_fields_from_standard_cv: List[str] = Field(default_factory=list,
                                                       description="Các mục thông tin còn thiếu so với CV mẫu.")
    extra_fields_in_user_cv: List[str] = Field(default_factory=list,
                                               description="Các mục thông tin có thêm trong CV người dùng so với CV mẫu.")
    comparison_summary: Optional[str] = Field(None, description="Tóm tắt so sánh giữa CV người dùng và CV mẫu.")
    missing_skills: List[str] = Field(default_factory=list, description="Danh sách kỹ năng còn thiếu so với vị trí mục tiêu.")
    extra_skills: List[str] = Field(default_factory=list, description="Danh sách kỹ năng bổ sung hoặc không liên quan trực tiếp.")
    overall_summary: Optional[str] = Field(None, description="Nhận xét tổng quan về sự phù hợp của ứng viên.")
    learning_path: Optional[str] = Field(None, description="Lộ trình học tập được đề xuất cho các kỹ năng còn thiếu.")
    suggested_problems: List[dict] = Field(default_factory=list, description="Danh sách các bài tập được gợi ý.")
    suggested_problems_count: int = Field(0, description="Số lượng bài tập được gợi ý.")
    suggested_level: Optional[int] = Field(None, description="Mức độ khó của bài tập được gợi ý.")
    suggested_language: Optional[str] = Field(None, description="Ngôn ngữ lập trình được gợi ý.")
    generated_cv_pdf: Optional[str] = None


# --- Pydantic Models for Exercises (JSON) ---
# Đây là model định nghĩa cấu trúc của một Exercise trong file JSON của bạn
class Exercise(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    level: int
    exercise_type: ExerciseType
    frontend_testcases: List[Any] = []
    backend_testcases: List[Any] = []

class SubmissionResult(BaseModel):
    test: str
    result: str

# --- Pydantic Models for CV Analysis ---
class ExtractedCVInfo(BaseModel):
    vi_tri_ung_tuyen: Optional[str] = None
    chuyen_nganh: Optional[str] = None
    so_nam_kinh_nghiem_tong_quan: Optional[str] = None
    ngon_ngu_the_manh: Optional[str] = None
    ky_nang_cong_nghe_khac: List[str] = []
    # ... và các trường khác của ExtractedCVInfo

class MatchedInfo(BaseModel):
    dang_bai_tap_goi_y: List[str]
    ngon_ngu_goi_y: str
    level_goi_y: int
    nhan_xet_tong_quan: Optional[str] = None
    extracted_cv_info: ExtractedCVInfo

class SuggestedProblemsResponse(MatchedInfo):
    suggested_problems: List[dict]
    suggested_problems_count: int


class UserUpdate(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None # Will be hashed in the logic before saving
    role: Optional[models.Role] = None

    class Config:
        from_attributes = True