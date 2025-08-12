import os
import json
from typing import List, Optional, Dict, Any
from pathlib import Path
  # Import Exercise từ models.py cùng cấp trong TestFE
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("Vui lòng cung cấp DATABASE_URL trong file .env")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Dependency để lấy DB session trong mỗi request
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
# Đường dẫn tới file JSON lưu trữ cơ sở dữ liệu các bài tập
# File này sẽ nằm cùng cấp với main.py trong thư mục scansCV
from models import Exercise
DB_FILE_PATH = Path("exercises_db.json")  # exercises_db.json sẽ nằm ở thư mục gốc của dự án


def _load_exercises_raw() -> List[Dict[str, Any]]:
    """
    Tải danh sách bài tập (dạng dict) từ file JSON.
    Trả về danh sách rỗng nếu file không tồn tại hoặc có lỗi.
    """
    if not DB_FILE_PATH.exists():
        return []
    try:
        with open(DB_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []  # Nếu file JSON không chứa một list
    except (json.JSONDecodeError, IOError):
        return []


def _save_exercises_raw(exercises_data: List[Dict[str, Any]]):
    """
    Lưu danh sách bài tập (dạng dict) vào file JSON.
    """
    try:
        with open(DB_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(exercises_data, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"Lỗi khi ghi file {DB_FILE_PATH}: {e}")


def get_all_exercises() -> List[Exercise]:
    """
    Lấy tất cả bài tập từ cơ sở dữ liệu JSON và chuyển đổi thành đối tượng Exercise.
    """
    exercises_data = _load_exercises_raw()
    return [Exercise(**data) for data in exercises_data]


def get_exercise_by_id(exercise_id: int) -> Optional[Exercise]:
    """
    Tìm và trả về một bài tập dựa trên ID của nó.
    Trả về None nếu không tìm thấy.
    """
    exercises_data = _load_exercises_raw()
    for data in exercises_data:
        if data.get("id") == exercise_id:
            try:
                return Exercise(**data)
            except Exception as e:  # Bắt lỗi validation của Pydantic nếu dữ liệu trong DB không khớp model
                print(f"Lỗi khi parse Exercise ID {exercise_id} từ DB: {e}")
                return None
    return None


def add_exercise(exercise: Exercise) -> int:
    """
    Thêm một bài tập mới vào cơ sở dữ liệu JSON hoặc cập nhật nếu ID đã tồn tại.
    Trả về ID của bài tập đã được thêm/cập nhật.
    """
    exercises_raw = _load_exercises_raw()

    # Kiểm tra xem exercise với ID này đã tồn tại chưa
    exercise_exists = False
    for i, ex_data in enumerate(exercises_raw):
        if ex_data.get("id") == exercise.id:
            exercises_raw[i] = exercise.model_dump()  # Cập nhật exercise hiện tại (Pydantic v2+)
            # exercises_raw[i] = exercise.dict() # Cho Pydantic v1
            exercise_exists = True
            print(f"Đã cập nhật bài tập với ID: {exercise.id}")
            break

    if not exercise_exists:
        exercises_raw.append(exercise.model_dump())  # Thêm exercise mới (Pydantic v2+)
        # exercises_raw.append(exercise.dict()) # Cho Pydantic v1
        print(f"Đã thêm bài tập mới với ID: {exercise.id}")

    _save_exercises_raw(exercises_raw)
    return exercise.id



