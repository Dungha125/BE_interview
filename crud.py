# crud.py
from typing import Optional

from sqlalchemy.orm import Session

import auth
import models
import schemas # Sẽ được tạo trong file main.py

def get_user(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()

def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()

def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()

# Hàm mới để kiểm tra xem có admin nào tồn tại không
def get_admin_user(db: Session):
    return db.query(models.User).filter(models.User.role == models.Role.ADMIN.value).first()

def create_user(db: Session, user: schemas.AdminUserCreate, hashed_password: str):
    db_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password,
        role = user.role.value
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def get_users(db):
    return db.query(models.User)


def update_user(db: Session, user_id: int, user_update: schemas.UserUpdate) -> Optional[models.User]:
    db_user = get_user(db, user_id)
    if not db_user:
        return None

    update_data = user_update.model_dump(exclude_unset=True)

    if "password" in update_data and update_data["password"]:
        hashed_password = auth.get_password_hash(update_data["password"])
        db_user.hashed_password = hashed_password
        del update_data["password"]  # Xóa khỏi dict để không cập nhật trực tiếp

    # Cập nhật các trường còn lại
    for key, value in update_data.items():
        setattr(db_user, key, value)

    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user