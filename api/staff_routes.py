"""Staff management: attendance, performance metrics, payroll."""

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_role
from db.models import AttendanceRecord, StaffMember, User
from db.session import get_db

router = APIRouter(prefix="/api/v2/staff", tags=["staff-management"])


class RegisterStaffRequest(BaseModel):
    name: str
    phone: str | None = None
    role: str = "cashier"
    hourly_rate: float = 0
    model_config = ConfigDict(json_schema_extra={"examples": [{"name": "Amit Sharma", "phone": "+919876543210", "role": "cashier", "hourly_rate": 125.0}]})


class ClockRequest(BaseModel):
    staff_code: str
    model_config = ConfigDict(json_schema_extra={"examples": [{"staff_code": "STAFF-12345"}]})


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
        select(StaffMember).where(StaffMember.store_id == user.store_id, StaffMember.is_active)
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


# ── Payroll Calculation ──

class PayrollConfig(BaseModel):
    overtime_multiplier: float = 1.5
    overtime_threshold_hours: float = 8.0
    pf_rate: float = 0.12  # 12% EPF
    esi_rate: float = 0.0075  # 0.75% ESI (employee share)
    professional_tax: float = 200  # Monthly PT
    bonus_pct: float = 0  # Optional bonus


@router.post("/payroll/calculate")
async def calculate_payroll(
    month: str,  # YYYY-MM format
    config: PayrollConfig = PayrollConfig(),
    user: User = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    """Calculate monthly payroll for all staff members.

    Includes overtime, PF, ESI, professional tax deductions.
    """
    # Get all active staff
    staff_result = await db.execute(
        select(StaffMember).where(StaffMember.is_active, StaffMember.store_id == user.store_id)
    )
    all_staff = staff_result.scalars().all()

    payroll_entries = []
    total_gross = 0
    total_deductions = 0
    total_net = 0

    for staff in all_staff:
        # Get attendance for the month
        att_result = await db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.staff_id == staff.id,
                AttendanceRecord.date.like(f"{month}%"),
            )
        )
        attendance = att_result.scalars().all()

        present_days = sum(1 for a in attendance if a.status in ("present", "late"))
        half_days = sum(1 for a in attendance if a.status == "half_day")
        total_hours = sum(a.hours_worked for a in attendance)

        # Calculate regular and overtime hours
        regular_hours = 0
        overtime_hours = 0
        for a in attendance:
            if a.hours_worked > config.overtime_threshold_hours:
                regular_hours += config.overtime_threshold_hours
                overtime_hours += a.hours_worked - config.overtime_threshold_hours
            else:
                regular_hours += a.hours_worked

        # Gross pay calculation
        regular_pay = regular_hours * staff.hourly_rate
        overtime_pay = overtime_hours * staff.hourly_rate * config.overtime_multiplier
        bonus = (regular_pay + overtime_pay) * config.bonus_pct / 100
        gross_pay = regular_pay + overtime_pay + bonus

        # Deductions
        pf_deduction = gross_pay * config.pf_rate
        esi_deduction = gross_pay * config.esi_rate
        professional_tax = config.professional_tax
        total_deduction = pf_deduction + esi_deduction + professional_tax

        net_pay = gross_pay - total_deduction

        entry = {
            "staff_code": staff.staff_code,
            "name": staff.name,
            "role": staff.role,
            "hourly_rate": staff.hourly_rate,
            "days_present": present_days,
            "half_days": half_days,
            "total_hours": round(total_hours, 1),
            "regular_hours": round(regular_hours, 1),
            "overtime_hours": round(overtime_hours, 1),
            "regular_pay": round(regular_pay, 2),
            "overtime_pay": round(overtime_pay, 2),
            "bonus": round(bonus, 2),
            "gross_pay": round(gross_pay, 2),
            "deductions": {
                "pf": round(pf_deduction, 2),
                "esi": round(esi_deduction, 2),
                "professional_tax": professional_tax,
                "total": round(total_deduction, 2),
            },
            "net_pay": round(net_pay, 2),
        }
        payroll_entries.append(entry)

        total_gross += gross_pay
        total_deductions += total_deduction
        total_net += net_pay

    return {
        "month": month,
        "staff_count": len(payroll_entries),
        "payroll": payroll_entries,
        "totals": {
            "gross_pay": round(total_gross, 2),
            "total_deductions": round(total_deductions, 2),
            "net_pay": round(total_net, 2),
        },
    }


@router.get("/attendance/summary")
async def attendance_summary(
    month: str = "",  # YYYY-MM
    user: User = Depends(require_role("manager")),
    db: AsyncSession = Depends(get_db),
):
    """Get monthly attendance summary for all staff."""
    if not month:
        month = time.strftime("%Y-%m")

    staff_result = await db.execute(
        select(StaffMember).where(StaffMember.is_active, StaffMember.store_id == user.store_id)
    )
    all_staff = staff_result.scalars().all()

    summaries = []
    for staff in all_staff:
        att_result = await db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.staff_id == staff.id,
                AttendanceRecord.date.like(f"{month}%"),
            )
        )
        records = att_result.scalars().all()

        present = sum(1 for r in records if r.status == "present")
        late = sum(1 for r in records if r.status == "late")
        absent = sum(1 for r in records if r.status == "absent")
        half_day = sum(1 for r in records if r.status == "half_day")
        total_hours = sum(r.hours_worked for r in records)

        summaries.append({
            "staff_code": staff.staff_code,
            "name": staff.name,
            "role": staff.role,
            "present": present,
            "late": late,
            "absent": absent,
            "half_day": half_day,
            "total_hours": round(total_hours, 1),
            "attendance_rate": round((present + late) / max(len(records), 1) * 100, 1),
        })

    return {"month": month, "staff_count": len(summaries), "summaries": summaries}
