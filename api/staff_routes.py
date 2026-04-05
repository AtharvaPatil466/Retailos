"""Staff management: attendance, performance metrics, payroll."""

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_role
from db.models import AttendanceRecord, Order, StaffMember, StaffShift, User
from db.session import get_db

router = APIRouter(prefix="/api/v2/staff", tags=["staff-management"])


class RegisterStaffRequest(BaseModel):
    name: str
    phone: str | None = None
    role: str = "cashier"
    hourly_rate: float = 0


class ClockRequest(BaseModel):
    staff_code: str


@router.post("/register")
async def register_staff(
    body: RegisterStaffRequest,
    user: User = Depends(require_role("manager")),
    db: AsyncSession = Depends(get_db),
):
    code = f"STAFF-{int(time.time()) % 100000}"
    staff = StaffMember(
        staff_code=code,
        name=body.name,
        phone=body.phone,
        role=body.role,
        hourly_rate=body.hourly_rate,
        store_id=user.store_id,
    )
    db.add(staff)
    await db.flush()
    return {"staff_code": code, "name": body.name, "role": body.role}


@router.get("")
async def list_staff(
    user: User = Depends(require_role("manager")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StaffMember).where(StaffMember.store_id == user.store_id, StaffMember.is_active == True)
    )
    staff = result.scalars().all()
    return {
        "staff": [
            {"id": s.id, "staff_code": s.staff_code, "name": s.name, "role": s.role, "hourly_rate": s.hourly_rate, "phone": s.phone}
            for s in staff
        ]
    }


# ── Attendance ──

@router.post("/clock-in")
async def clock_in(
    body: ClockRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(StaffMember).where(StaffMember.staff_code == body.staff_code))
    staff = result.scalar_one_or_none()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff not found")

    today = time.strftime("%Y-%m-%d")
    existing = await db.execute(
        select(AttendanceRecord).where(AttendanceRecord.staff_id == staff.id, AttendanceRecord.date == today)
    )
    record = existing.scalar_one_or_none()

    if record and record.clock_in:
        raise HTTPException(status_code=400, detail="Already clocked in today")

    if not record:
        record = AttendanceRecord(staff_id=staff.id, date=today)
        db.add(record)

    record.clock_in = time.time()
    record.status = "present"
    await db.flush()

    return {"staff_code": body.staff_code, "name": staff.name, "clock_in": record.clock_in, "date": today}


@router.post("/clock-out")
async def clock_out(
    body: ClockRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(StaffMember).where(StaffMember.staff_code == body.staff_code))
    staff = result.scalar_one_or_none()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff not found")

    today = time.strftime("%Y-%m-%d")
    existing = await db.execute(
        select(AttendanceRecord).where(AttendanceRecord.staff_id == staff.id, AttendanceRecord.date == today)
    )
    record = existing.scalar_one_or_none()

    if not record or not record.clock_in:
        raise HTTPException(status_code=400, detail="Not clocked in today")

    record.clock_out = time.time()
    record.hours_worked = round((record.clock_out - record.clock_in) / 3600, 2)

    if record.hours_worked < 4:
        record.status = "half_day"

    await db.flush()

    return {"staff_code": body.staff_code, "hours_worked": record.hours_worked, "status": record.status}


@router.get("/attendance")
async def get_attendance(
    date: str | None = None,
    user: User = Depends(require_role("manager")),
    db: AsyncSession = Depends(get_db),
):
    target_date = date or time.strftime("%Y-%m-%d")
    result = await db.execute(
        select(AttendanceRecord, StaffMember)
        .join(StaffMember, AttendanceRecord.staff_id == StaffMember.id)
        .where(AttendanceRecord.date == target_date, StaffMember.store_id == user.store_id)
    )
    rows = result.all()

    return {
        "date": target_date,
        "records": [
            {
                "staff_code": staff.staff_code,
                "name": staff.name,
                "role": staff.role,
                "clock_in": record.clock_in,
                "clock_out": record.clock_out,
                "hours_worked": record.hours_worked,
                "status": record.status,
            }
            for record, staff in rows
        ],
    }


# ── Performance Metrics ──

@router.get("/performance/{staff_code}")
async def get_staff_performance(
    staff_code: str,
    days: int = 30,
    user: User = Depends(require_role("manager")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(StaffMember).where(StaffMember.staff_code == staff_code))
    staff = result.scalar_one_or_none()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff not found")

    cutoff_date = time.strftime("%Y-%m-%d", time.localtime(time.time() - days * 86400))

    # Attendance stats
    att_result = await db.execute(
        select(AttendanceRecord).where(AttendanceRecord.staff_id == staff.id, AttendanceRecord.date >= cutoff_date)
    )
    attendance = att_result.scalars().all()

    total_days = len(attendance)
    present_days = sum(1 for a in attendance if a.status in ("present", "late"))
    total_hours = sum(a.hours_worked for a in attendance)

    return {
        "staff_code": staff_code,
        "name": staff.name,
        "role": staff.role,
        "period_days": days,
        "attendance": {
            "total_days": total_days,
            "present_days": present_days,
            "absent_days": total_days - present_days,
            "attendance_rate": round(present_days / max(total_days, 1) * 100, 1),
            "total_hours": round(total_hours, 1),
            "avg_hours_per_day": round(total_hours / max(present_days, 1), 1),
        },
        "payroll_estimate": {
            "hourly_rate": staff.hourly_rate,
            "total_hours": round(total_hours, 1),
            "gross_pay": round(total_hours * staff.hourly_rate, 2),
        },
    }
