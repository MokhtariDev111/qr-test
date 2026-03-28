from fastapi import APIRouter
from app.api.routes import auth, courses, attendance

router = APIRouter(prefix="/api")
router.include_router(auth.router)
router.include_router(courses.router)
router.include_router(attendance.router)
