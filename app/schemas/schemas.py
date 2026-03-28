from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: str = "student"
    student_id: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    student_id: Optional[str]

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class CourseCreate(BaseModel):
    code: str
    name: str
    day_of_week: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None


class CourseResponse(BaseModel):
    id: int
    code: str
    name: str
    teacher_id: int
    day_of_week: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None

    class Config:
        from_attributes = True


class SessionCreate(BaseModel):
    course_id: int
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class SessionResponse(BaseModel):
    id: int
    course_id: int
    is_active: bool
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    class Config:
        from_attributes = True


class QRResponse(BaseModel):
    session_id: int
    qr_image: str
    expires_in: int
    qr_text: Optional[str] = None


class ScanRequest(BaseModel):
    qr_token: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_accuracy: Optional[float] = None  # GPS accuracy in meters
    device_id: Optional[str] = None

class TeacherLocationRequest(BaseModel):
    latitude: float
    longitude: float

