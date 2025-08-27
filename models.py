# models.py
import enum

from pydantic import BaseModel, Field
from typing import List, Optional, Any
from enum import Enum


# Enum để phân loại bài tập
class ExerciseType(str, Enum):
    FRONTEND = "frontend"
    BACKEND = "backend"

class Role(str, enum.Enum):
    ADMIN = "admin"
    LECTURER = "lecturer"
    STUDENT = "student"


# Model cho test case của backend (Input/Output)
class BackendTestCase(BaseModel):
    id: int
    stdin: str = Field(..., description="Dữ liệu đầu vào chuẩn (standard input).")
    expected_stdout: str = Field(..., description="Kết quả đầu ra chuẩn mong đợi (standard output).")


# Model cho test case của frontend (giữ nguyên từ cấu trúc cũ của bạn)
class FrontendTestCase(BaseModel):
    id: int
    name: str
    type: str
    selector: Optional[str] = None
    trigger: Optional[str] = None
    expected: Optional[str] = None
    attributeName: Optional[str] = None
    is_frontend: bool = True


# Cập nhật model Exercise chính
class Exercise(BaseModel):
    id: int
    title: str
    description: Optional[str] = None

    # Trường để xác định loại bài tập, mặc định là backend
    exercise_type: ExerciseType = ExerciseType.BACKEND

    # Tách biệt test cases để dễ quản lý
    backend_testcases: Optional[List[BackendTestCase]] = Field(default_factory=list)
    frontend_testcases: Optional[List[FrontendTestCase]] = Field(default_factory=list)


# Model cho kết quả nộp bài (giữ nguyên)
class SubmissionResult(BaseModel):
    test: str
    result: str

#Model cho user
from sqlalchemy import Column, Integer, String, Boolean
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    role = Column(String, default=Role.STUDENT.value, nullable=False)