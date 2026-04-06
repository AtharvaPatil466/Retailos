"""Image-based shelf audit analysis.

Analyzes shelf photos to check planogram compliance, detect gaps,
and estimate stock levels. Uses Gemini Vision API when configured,
falls back to rule-based mock analysis for demo mode.
"""

import json
import logging
import os
import time
import base64
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class ShelfAuditor:
    """Camera-based shelf compliance checker."""

    def __init__(self):
        self.gemini_key = os.environ.get("GEMINI_API_KEY", "")
        self._audit_log: list[dict] = []

    @property
    def is_configured(self) -> bool:
        return bool(self.gemini_key)

    async def analyze_shelf_image(
        self,
        image_base64: str,
        zone_id: str = "",
        zone_name: str = "",
    ) -> dict[str, Any]:
        """Analyze a shelf image for compliance issues.

        Args:
            image_base64: Base64-encoded image data
            zone_id: Optional zone identifier
            zone_name: Optional zone name for context
        """
        if self.is_configured and image_base64:
            return await self._analyze_with_gemini(image_base64, zone_id, zone_name)
        return self._mock_analysis(zone_id, zone_name)

    async def _analyze_with_gemini(
        self,
        image_base64: str,
        zone_id: str,
        zone_name: str,
    ) -> dict:
        """Use Gemini Vision to analyze shelf image."""
        try:
            from google import genai

            client = genai.Client(api_key=self.gemini_key)

            prompt = f"""Analyze this retail store shelf image for zone '{zone_name or zone_id}'.
            Check for:
            1. Empty shelf spaces / stock gaps
            2. Products placed in wrong sections
            3. Price tag visibility
            4. Shelf cleanliness and organization
            5. Product facing (are labels visible?)
            6. Expired or damaged products visible

            Return a JSON object with:
            - overall_score (0-100)
            - issues (list of findings)
            - recommendations (list of actions)
            - stock_level_estimate (low/medium/high)
            - compliance_status (compliant/needs_attention/non_compliant)
            """

            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": image_base64}},
                ],
            )

            # Parse response
            text = response.text
            try:
                # Try to extract JSON from response
                start = text.find("{")
                end = text.rfind("}") + 1
                if start >= 0 and end > start:
                    result = json.loads(text[start:end])
                else:
                    result = {"raw_analysis": text}
            except json.JSONDecodeError:
                result = {"raw_analysis": text}

            result["zone_id"] = zone_id
            result["zone_name"] = zone_name
            result["analyzed_at"] = time.time()
            result["method"] = "gemini_vision"
            self._audit_log.append(result)
            return result

        except Exception as e:
            logger.warning("Gemini shelf analysis failed: %s", e)
            return self._mock_analysis(zone_id, zone_name, error=str(e))

    def _mock_analysis(self, zone_id: str, zone_name: str, error: str = "") -> dict:
        """Generate mock shelf audit for demo mode."""
        import random

        score = random.randint(55, 95)
        issues = []
        recommendations = []

        if score < 70:
            issues.extend([
                {"type": "stock_gap", "severity": "high", "description": "Empty shelf space detected in top row, left section"},
                {"type": "misplaced", "severity": "medium", "description": "Cleaning products found in food section"},
                {"type": "price_tag", "severity": "low", "description": "2 products missing price tags"},
            ])
            recommendations.extend([
                "Restock top row immediately — high-visibility area",
                "Move cleaning products to correct zone",
                "Print and attach missing price tags",
            ])
        elif score < 85:
            issues.extend([
                {"type": "facing", "severity": "low", "description": "3 products have labels facing sideways"},
                {"type": "organization", "severity": "low", "description": "Products not aligned to shelf edge"},
            ])
            recommendations.extend([
                "Rotate products to face labels forward",
                "Align products to shelf edge for neat appearance",
            ])
        else:
            issues.append({"type": "none", "severity": "info", "description": "Shelf looks well-organized"})
            recommendations.append("Maintain current standards")

        stock_levels = {range(0, 60): "low", range(60, 80): "medium", range(80, 101): "high"}
        stock_level = next((v for k, v in stock_levels.items() if score in k), "medium")

        compliance = "compliant" if score >= 80 else "needs_attention" if score >= 60 else "non_compliant"

        result = {
            "zone_id": zone_id,
            "zone_name": zone_name,
            "overall_score": score,
            "stock_level_estimate": stock_level,
            "compliance_status": compliance,
            "issues": issues,
            "recommendations": recommendations,
            "analyzed_at": time.time(),
            "method": "demo_mock",
        }
        if error:
            result["fallback_reason"] = error

        self._audit_log.append(result)
        return result

    def get_audit_log(self, limit: int = 50) -> list[dict]:
        return self._audit_log[-limit:]

    def get_compliance_summary(self) -> dict:
        """Get summary of recent shelf audits."""
        if not self._audit_log:
            return {"total_audits": 0, "avg_score": 0}

        scores = [a.get("overall_score", 0) for a in self._audit_log]
        statuses = [a.get("compliance_status", "") for a in self._audit_log]
        return {
            "total_audits": len(self._audit_log),
            "avg_score": round(sum(scores) / len(scores), 1),
            "compliant_pct": round(statuses.count("compliant") / len(statuses) * 100, 1),
            "needs_attention": statuses.count("needs_attention"),
            "non_compliant": statuses.count("non_compliant"),
        }


shelf_auditor = ShelfAuditor()
