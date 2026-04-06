"""Shelf audit API endpoints."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth.dependencies import require_role
from db.models import User
from brain.shelf_audit import shelf_auditor

router = APIRouter(prefix="/api/shelf-audit", tags=["ml-intelligence"])


class ShelfImageRequest(BaseModel):
    image_base64: str = ""
    zone_id: str = ""
    zone_name: str = ""


@router.post("/analyze")
async def analyze_shelf(
    body: ShelfImageRequest,
    user: User = Depends(require_role("staff")),
):
    """Analyze a shelf image for compliance issues.

    Upload a base64-encoded shelf photo for AI-powered analysis.
    Returns compliance score, detected issues, and recommendations.
    """
    return await shelf_auditor.analyze_shelf_image(
        image_base64=body.image_base64,
        zone_id=body.zone_id,
        zone_name=body.zone_name,
    )


@router.get("/status")
async def audit_status():
    """Get shelf audit service status."""
    return {
        "is_configured": shelf_auditor.is_configured,
        "method": "gemini_vision" if shelf_auditor.is_configured else "demo_mock",
    }


@router.get("/log")
async def audit_log(
    limit: int = 50,
    user: User = Depends(require_role("staff")),
):
    """Get recent shelf audit history."""
    return {"audits": shelf_auditor.get_audit_log(limit)}


@router.get("/summary")
async def compliance_summary(
    user: User = Depends(require_role("manager")),
):
    """Get compliance summary across all audits."""
    return shelf_auditor.get_compliance_summary()
