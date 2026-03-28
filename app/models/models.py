from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Float, UniqueConstraint
from app.core.database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    full_name = Column(String)
    role = Column(String, default="student")
    student_id = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Course(Base):
    __tablename__ = "courses"
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True)
    name = Column(String)
    teacher_id = Column(Integer, ForeignKey("users.id"))
    day_of_week = Column(String, nullable=True)   # e.g. "Monday"
    start_time = Column(String, nullable=True)    # e.g. "08:30"
    end_time = Column(String, nullable=True)      # e.g. "10:00"


class Enrollment(Base):
    __tablename__ = "enrollments"
    id = Column(Integer, primary_key=True)
    course_id = Column(Integer, ForeignKey("courses.id"))
    student_id = Column(Integer, ForeignKey("users.id"))


class AttendanceSession(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True)
    course_id = Column(Integer, ForeignKey("courses.id"))
    teacher_id = Column(Integer, ForeignKey("users.id"))
    qr_token = Column(String, unique=True)
    last_qr_token = Column(String, nullable=True)
    qr_expires_at = Column(DateTime)
    is_active = Column(Boolean, default=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Attendance(Base):
    __tablename__ = "attendances"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("sessions.id"))
    student_id = Column(Integer, ForeignKey("users.id"))
    qr_verified = Column(Boolean, default=False)
    is_present = Column(Boolean, default=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    location_accuracy = Column(Float, nullable=True)  # GPS accuracy in meters
    device_id = Column(String, nullable=True)
    marked_at = Column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint('session_id', 'student_id', name='_session_student_uc'),)
