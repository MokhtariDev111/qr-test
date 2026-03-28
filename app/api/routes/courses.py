from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core import get_db
from app.models import User, Course, Enrollment
from app.schemas import CourseCreate, CourseResponse
from app.api.routes.auth import get_current_user, require_teacher

# NOTE: routes use "" (no trailing slash) to prevent FastAPI 307 redirects
# that strip the Authorization header on POST/GET requests.
router = APIRouter(prefix="/courses", tags=["Courses"])


@router.post("", response_model=CourseResponse)
async def create_course(data: CourseCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_teacher)):
    result = await db.execute(select(Course).where(Course.code == data.code))
    if result.scalar_one_or_none():
        raise HTTPException(400, "Code exists")
    course = Course(
        code=data.code,
        name=data.name,
        teacher_id=user.id,
        day_of_week=data.day_of_week,
        start_time=data.start_time,
        end_time=data.end_time,
    )
    db.add(course)
    await db.commit()
    await db.refresh(course)
    return course


@router.get("", response_model=List[CourseResponse])
async def list_courses(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role == "teacher":
        result = await db.execute(select(Course).where(Course.teacher_id == user.id))
    else:
        result = await db.execute(select(Course).join(Enrollment).where(Enrollment.student_id == user.id))
    return result.scalars().all()


@router.post("/{course_id}/enroll/{student_id}")
async def enroll(course_id: int, student_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_teacher)):
    result = await db.execute(select(Course).where(Course.id == course_id, Course.teacher_id == user.id))
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Course not found")
    result = await db.execute(select(Enrollment).where(Enrollment.course_id == course_id, Enrollment.student_id == student_id))
    if result.scalar_one_or_none():
        raise HTTPException(400, "Already enrolled")
    db.add(Enrollment(course_id=course_id, student_id=student_id))
    await db.commit()
    return {"message": "Enrolled"}


@router.put("/{course_id}", response_model=CourseResponse)
async def update_course(course_id: int, data: CourseCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_teacher)):
    result = await db.execute(select(Course).where(Course.id == course_id, Course.teacher_id == user.id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(404, "Course not found")
        
    course.code = data.code
    course.name = data.name
    course.day_of_week = data.day_of_week
    course.start_time = data.start_time
    course.end_time = data.end_time
    await db.commit()
    await db.refresh(course)
    return course


@router.delete("/{course_id}")
async def delete_course(course_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_teacher)):
    result = await db.execute(select(Course).where(Course.id == course_id, Course.teacher_id == user.id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(404, "Course not found")
    
    # Needs to delete enrollments and sessions as well to keep DB clean
    from app.models import AttendanceSession, Attendance
    await db.execute(select(Attendance).join(AttendanceSession).where(AttendanceSession.course_id == course_id))
    
    # For now, simplistic deletion
    await db.delete(course)
    await db.commit()
    return {"success": True}
