import math
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
import io
from fpdf import FPDF
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
import asyncio
from app.core import get_db, settings, async_session
from app.core.security import decode_token
from app.models import User, Course, Enrollment, AttendanceSession, Attendance
from app.schemas import SessionCreate, SessionResponse, QRResponse, ScanRequest, TeacherLocationRequest
from app.services import qr_service
from app.api.routes.auth import get_current_user, require_teacher, require_student
router = APIRouter(prefix="/attendance", tags=["Attendance"])


def calculate_distance(lat1, lon1, lat2, lon2):
    """Haversine distance in meters"""
    if None in [lat1, lon1, lat2, lon2]: return 0
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


@router.post("/sessions", response_model=SessionResponse)
async def create_session(data: SessionCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_teacher)):
    result = await db.execute(select(Course).where(Course.id == data.course_id, Course.teacher_id == user.id))
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Course not found")
    token = qr_service.generate_qr_token()
    session = AttendanceSession(
        course_id=data.course_id, 
        teacher_id=user.id, 
        qr_token=token, 
        qr_expires_at=qr_service.get_qr_expiry(),
        latitude=None,
        longitude=None
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.post("/sessions/{session_id}/set-location")
async def set_teacher_location(session_id: int, data: TeacherLocationRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_teacher)):
    """Teacher scans QR on phone to set accurate GPS location"""
    result = await db.execute(select(AttendanceSession).where(
        AttendanceSession.id == session_id, 
        AttendanceSession.teacher_id == user.id,
        AttendanceSession.is_active == True
    ))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")
    
    if not data.latitude or not data.longitude:
        raise HTTPException(400, "Location required! Please enable GPS.")
    
    session.latitude = data.latitude
    session.longitude = data.longitude
    await db.commit()
    
    return {"message": "Classroom location set!", "latitude": data.latitude, "longitude": data.longitude}


@router.get("/sessions/{session_id}/qr", response_model=QRResponse)
async def get_qr(session_id: int, origin: str, db: AsyncSession = Depends(get_db), user: User = Depends(require_teacher)):
    result = await db.execute(select(AttendanceSession).where(AttendanceSession.id == session_id, AttendanceSession.teacher_id == user.id, AttendanceSession.is_active == True))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")
    session.last_qr_token = session.qr_token
    session.qr_token = qr_service.generate_qr_token()
    session.qr_expires_at = qr_service.get_qr_expiry()
    await db.commit()
    return QRResponse(
        session_id=session_id, 
        qr_image=qr_service.generate_qr_image(session_id, session.qr_token, origin), 
        expires_in=settings.qr_refresh_interval,
        qr_text=f"{session_id}:{session.qr_token}"
    )


@router.post("/sessions/{session_id}/end")
async def end_session(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_teacher)):
    result = await db.execute(select(AttendanceSession).where(AttendanceSession.id == session_id, AttendanceSession.teacher_id == user.id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")
    session.is_active = False
    await db.commit()
    return {"message": "Ended"}


@router.get("/sessions/{session_id}/records")
async def get_records(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_teacher)):
    result = await db.execute(select(Attendance, User).join(User, Attendance.student_id == User.id).where(Attendance.session_id == session_id))
    return [{"id": a.id, "student_id": a.student_id, "student_name": u.full_name, "is_present": a.is_present, "marked_at": a.marked_at} for a, u in result.all()]


@router.get("/sessions/{session_id}/locations")
async def get_student_locations(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_teacher)):
    """Get GPS locations of all students who scanned in this session."""
    result_session = await db.execute(select(AttendanceSession).where(AttendanceSession.id == session_id))
    session = result_session.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")

    result = await db.execute(
        select(Attendance, User)
        .join(User, Attendance.student_id == User.id)
        .where(Attendance.session_id == session_id, Attendance.is_present == True)
    )
    
    locations = []
    for a, u in result.all():
        if a.latitude and a.longitude:
            dist = 0
            if session.latitude and session.longitude:
                dist = calculate_distance(session.latitude, session.longitude, a.latitude, a.longitude)
            locations.append({
                "student_name": u.full_name,
                "student_id": u.student_id,
                "latitude": a.latitude,
                "longitude": a.longitude,
                "location_accuracy_meters": int(a.location_accuracy) if a.location_accuracy else None,
                "marked_at": a.marked_at,
                "distance_meters": int(dist)
            })
    
    return {
        "teacher_location_set": session.latitude is not None and session.longitude is not None,
        "teacher_lat": session.latitude,
        "teacher_lng": session.longitude,
        "students": locations
    }

@router.post("/scan")
async def scan(data: ScanRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_student)):
    # REQUIRE GPS - Student must enable location
    if not data.latitude or not data.longitude:
        raise HTTPException(400, "📍 Location required! Please enable GPS in your phone settings and try again.")
    
    if data.location_accuracy and data.location_accuracy > 500:
        raise HTTPException(400, f"📍 GPS accuracy too poor ({int(data.location_accuracy)}m). Please enable precise GPS or go outside.")
    
    parts = data.qr_token.split(":")
    if len(parts) != 2:
        raise HTTPException(400, "Invalid QR")
    session_id, token = int(parts[0]), parts[1]
    print(f"DEBUG: Scan attempt by {user.full_name} for session {session_id} with token {token[:10]}...")
    result = await db.execute(select(AttendanceSession).where(AttendanceSession.id == session_id, AttendanceSession.is_active == True))
    session = result.scalar_one_or_none()
    
    if not session:
        print(f"DEBUG: Session {session_id} not found or inactive")
        raise HTTPException(400, "Session not found or ended")
        
    if session.qr_token != token and session.last_qr_token != token:
        print(f"DEBUG: Token mismatch. Expected {session.qr_token[:10]}... or {session.last_qr_token[:10] if session.last_qr_token else 'None'}... got {token[:10]}...")
        raise HTTPException(400, "Invalid QR code (it may have just refreshed)")

    if session.qr_expires_at < datetime.utcnow() and (datetime.utcnow() - session.qr_expires_at).total_seconds() > 10:
        print(f"DEBUG: Token expired at {session.qr_expires_at}. Current time {datetime.utcnow()}")
        raise HTTPException(400, "QR code expired")
    
    # Check if teacher has set location
    if not session.latitude or not session.longitude:
        raise HTTPException(400, "⏳ Teacher hasn't set classroom location yet. Please wait.")
    
    dist_val = None
    # GPS Distance check - 15 meters limit
    if session.latitude and session.longitude and data.latitude and data.longitude:
        dist_val = calculate_distance(session.latitude, session.longitude, data.latitude, data.longitude)
        print(f"DEBUG: Distance check for {user.full_name}: {dist_val:.1f} meters")
        
        if dist_val > 15:
            raise HTTPException(400, f"🚫 You are {int(dist_val)} meters away from the classroom. You must be within 15 meters to mark attendance.")

    # Anti-Multiple-Account (Fingerprint) check
    if data.device_id:
        existing_res = await db.execute(select(Attendance).where(Attendance.session_id == session_id, Attendance.device_id == data.device_id, Attendance.student_id != user.id))
        if existing_res.scalar_one_or_none():
            raise HTTPException(400, "Device already used by another student for this session!")

    result = await db.execute(select(Enrollment).where(Enrollment.course_id == session.course_id, Enrollment.student_id == user.id))
    if not result.scalar_one_or_none():
        db.add(Enrollment(course_id=session.course_id, student_id=user.id))
        await db.flush()
    result = await db.execute(select(Attendance).where(Attendance.session_id == session_id, Attendance.student_id == user.id))
    att = result.scalar_one_or_none()
    if att and att.is_present:
        raise HTTPException(400, "Already marked")
    if not att:
        att = Attendance(session_id=session_id, student_id=user.id)
        db.add(att)
    
    att.qr_verified = True
    att.is_present = True
    att.latitude = data.latitude
    att.longitude = data.longitude
    att.location_accuracy = data.location_accuracy
    att.device_id = data.device_id
    att.marked_at = datetime.utcnow()
    
    await db.commit()
    return {
        "message": "✅ Attendance marked successfully!", 
        "session_id": session_id,
        "distance_meters": int(dist_val) if dist_val is not None else None,
        "location_accuracy_meters": int(data.location_accuracy) if data.location_accuracy else None
    }


@router.get("/sessions/{session_id}/report")
async def export_report(session_id: int, token: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    current_user = None
    if token:
        payload = decode_token(token)
        if payload and str(payload.get("sub", "")).isdigit():
            res = await db.execute(select(User).where(User.id == int(payload.get("sub"))))
            current_user = res.scalar_one_or_none()

    if not current_user or current_user.role != "teacher":
        raise HTTPException(403, "Access denied")

    res = await db.execute(select(AttendanceSession, Course).join(Course, Course.id == AttendanceSession.course_id).where(AttendanceSession.id == session_id, AttendanceSession.teacher_id == current_user.id))
    entry = res.one_or_none()
    if not entry: raise HTTPException(404, "Session not found")
    session, course = entry
    
    attendees_res = await db.execute(select(Attendance, User).join(User, Attendance.student_id == User.id).where(Attendance.session_id == session_id, Attendance.is_present == True))
    attendees = attendees_res.all()
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 20)
    pdf.cell(0, 15,f"Attendance Report: {course.name}", ln=True, align="C")
    
    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 10, f"Course Code: {course.code}", ln=True)
    pdf.cell(0, 10, f"Date: {session.created_at.strftime('%Y-%m-%d %H:%M')}", ln=True)
    pdf.cell(0, 10, f"Total Present: {len(attendees)}", ln=True)
    pdf.ln(10)
    
    pdf.set_font("Arial", "B", 12)
    pdf.cell(40, 10, "Student ID", 1)
    pdf.cell(80, 10, "Name", 1)
    pdf.cell(60, 10, "Time Marked", 1)
    pdf.ln()
    
    pdf.set_font("Arial", "", 11)
    for att, u in attendees:
        pdf.cell(40, 10, str(u.student_id or "N/A"), 1)
        pdf.cell(80, 10, str(u.full_name), 1)
        pdf.cell(60, 10, att.marked_at.strftime("%H:%M:%S") if att.marked_at else "-", 1)
        pdf.ln()
        
    out = io.BytesIO(pdf.output())
    filename = f"Attendance_{course.code}_{session.created_at.strftime('%Y%m%d')}.pdf"
    return StreamingResponse(out, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={filename}"})


@router.get("/my-history")
async def history(db: AsyncSession = Depends(get_db), user: User = Depends(require_student)):
    result = await db.execute(select(Attendance).where(Attendance.student_id == user.id).order_by(Attendance.id.desc()))
    return result.scalars().all()


@router.get("/teacher-history")
async def teacher_history(db: AsyncSession = Depends(get_db), user: User = Depends(require_teacher)):
    result = await db.execute(
        select(AttendanceSession, Course)
        .join(Course, Course.id == AttendanceSession.course_id)
        .where(AttendanceSession.teacher_id == user.id)
        .order_by(AttendanceSession.id.desc())
    )
    return [{
        "id": s.id,
        "course_name": c.name,
        "course_code": c.code,
        "created_at": s.created_at,
        "is_active": s.is_active
    } for s, c in result.all()]


@router.post("/sessions/{session_id}/clear")
async def clear_attendance(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_teacher)):
    result = await db.execute(select(AttendanceSession).where(AttendanceSession.id == session_id, AttendanceSession.teacher_id == user.id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")
    await db.execute(delete(Attendance).where(Attendance.session_id == session_id))
    await db.commit()
    return {"message": "Attendance records cleared"}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_teacher)):
    result = await db.execute(select(AttendanceSession).where(AttendanceSession.id == session_id, AttendanceSession.teacher_id == user.id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")
    await db.execute(delete(Attendance).where(Attendance.session_id == session_id))
    await db.delete(session)
    await db.commit()
    return {"success": True}


@router.websocket("/ws/{session_id}")
async def ws_qr(websocket: WebSocket, session_id: int, origin: str = "http://localhost:5173"):
    await websocket.accept()
    try:
        while True:
            await asyncio.sleep(settings.qr_refresh_interval)
            async with async_session() as db:
                result = await db.execute(select(AttendanceSession).where(AttendanceSession.id == session_id, AttendanceSession.is_active == True))
                session = result.scalar_one_or_none()
                if not session:
                    await websocket.send_json({"type": "ended"})
                    break
                session.last_qr_token = session.qr_token
                session.qr_token = qr_service.generate_qr_token()
                session.qr_expires_at = qr_service.get_qr_expiry()
                await db.commit()
                await websocket.send_json({
                    "type": "refresh", 
                    "qr_image": qr_service.generate_qr_image(session_id, session.qr_token, origin),
                    "qr_text": f"{session_id}:{session.qr_token}"
                })
    except WebSocketDisconnect:
        pass