"""DPDP Act (Digital Personal Data Protection) compliance utilities.

India's DPDP Act 2023 requirements:
- Purpose limitation: collect data only for stated purposes
- Data minimization: don't collect unnecessary data
- Right to access: users can request their data
- Right to correction: users can correct their data
- Right to erasure: users can request deletion
- Consent management: track consent for data processing
- Data breach notification: notify within 72 hours
- Data Processing Impact Assessment (DPIA)

Also covers GDPR-equivalent requirements for international compliance.
"""

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


# Data retention periods (in days)
RETENTION_POLICIES = {
    "transaction_data": 365 * 8,    # 8 years (GST requirement)
    "customer_pii": 365 * 3,        # 3 years after last transaction
    "audit_logs": 365 * 5,          # 5 years
    "session_data": 30,              # 30 days
    "notification_logs": 90,         # 90 days
    "analytics_data": 365 * 2,      # 2 years
    "backup_data": 365,             # 1 year
}

# Purpose registry — what data is collected and why
PURPOSE_REGISTRY = {
    "billing": {
        "description": "Processing orders, payments, and generating invoices",
        "data_collected": ["name", "phone", "email", "address", "payment_details"],
        "legal_basis": "contractual_necessity",
        "retention": "8 years (GST compliance)",
    },
    "delivery": {
        "description": "Delivering orders to customer address",
        "data_collected": ["name", "phone", "address"],
        "legal_basis": "contractual_necessity",
        "retention": "Until delivery completed + 90 days",
    },
    "marketing": {
        "description": "Sending promotional offers and loyalty updates",
        "data_collected": ["name", "phone", "email", "purchase_history"],
        "legal_basis": "consent",
        "retention": "Until consent withdrawn",
    },
    "analytics": {
        "description": "Understanding purchase patterns for inventory planning",
        "data_collected": ["purchase_history", "category_preferences"],
        "legal_basis": "legitimate_interest",
        "retention": "2 years (anonymized after)",
    },
    "credit_management": {
        "description": "Managing udhaar/credit accounts",
        "data_collected": ["name", "phone", "credit_history"],
        "legal_basis": "contractual_necessity",
        "retention": "Until balance cleared + 3 years",
    },
}


class DPDPComplianceManager:
    """DPDP Act compliance management."""

    def __init__(self):
        self._consent_log: list[dict] = []
        self._data_requests: list[dict] = []
        self._breach_log: list[dict] = []

    def record_consent(
        self,
        customer_id: str,
        purpose: str,
        consented: bool,
        channel: str = "in_app",
    ) -> dict:
        """Record customer consent for a specific data processing purpose."""
        entry = {
            "customer_id": customer_id,
            "purpose": purpose,
            "consented": consented,
            "channel": channel,
            "timestamp": time.time(),
            "ip_address": "",  # Should be set by caller
        }
        self._consent_log.append(entry)
        return entry

    def check_consent(self, customer_id: str, purpose: str) -> bool:
        """Check if customer has given consent for a purpose."""
        # Find most recent consent entry for this customer/purpose
        for entry in reversed(self._consent_log):
            if entry["customer_id"] == customer_id and entry["purpose"] == purpose:
                return entry["consented"]
        return False

    def get_consent_history(self, customer_id: str) -> list[dict]:
        """Get all consent records for a customer."""
        return [e for e in self._consent_log if e["customer_id"] == customer_id]

    def generate_data_export(self, customer_data: dict[str, Any]) -> dict:
        """Generate a DPDP-compliant data export for Right to Access requests.

        Returns all personal data held about a customer in a portable format.
        """
        export = {
            "export_type": "DPDP_DATA_ACCESS_REQUEST",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "data_controller": "RetailOS",
            "categories": {},
        }

        if "personal_info" in customer_data:
            export["categories"]["personal_information"] = {
                "data": customer_data["personal_info"],
                "purpose": "Account management and billing",
                "source": "Customer registration",
            }

        if "purchase_history" in customer_data:
            export["categories"]["transaction_history"] = {
                "data": customer_data["purchase_history"],
                "purpose": "Order fulfillment and billing",
                "retention": "8 years (GST requirement)",
            }

        if "loyalty_data" in customer_data:
            export["categories"]["loyalty_program"] = {
                "data": customer_data["loyalty_data"],
                "purpose": "Loyalty rewards management",
            }

        if "credit_data" in customer_data:
            export["categories"]["credit_account"] = {
                "data": customer_data["credit_data"],
                "purpose": "Credit/udhaar management",
            }

        if "consent_records" in customer_data:
            export["categories"]["consent_records"] = {
                "data": customer_data["consent_records"],
                "purpose": "Compliance record-keeping",
            }

        return export

    def request_data_erasure(self, customer_id: str, reason: str = "") -> dict:
        """Process a Right to Erasure (Right to be Forgotten) request.

        Note: Some data must be retained for legal compliance (GST records).
        """
        request = {
            "request_id": f"ERASE-{int(time.time())}",
            "customer_id": customer_id,
            "reason": reason,
            "status": "pending_review",
            "timestamp": time.time(),
            "retention_exceptions": [
                "Transaction data retained for 8 years (GST compliance)",
                "Audit logs retained for 5 years (legal requirement)",
            ],
            "data_to_delete": [
                "Marketing preferences",
                "Analytics cookies",
                "Push notification subscriptions",
                "Non-essential profile data",
            ],
            "data_to_anonymize": [
                "Purchase history (name → anonymized ID)",
                "Delivery addresses (after order completion)",
            ],
        }
        self._data_requests.append(request)
        return request

    def log_data_breach(
        self,
        description: str,
        affected_records: int,
        data_types: list[str],
        severity: str = "medium",
    ) -> dict:
        """Log a data breach incident (must notify within 72 hours per DPDP Act)."""
        breach = {
            "breach_id": f"BREACH-{int(time.time())}",
            "description": description,
            "affected_records": affected_records,
            "data_types": data_types,
            "severity": severity,
            "detected_at": time.time(),
            "notification_deadline": time.time() + 72 * 3600,  # 72 hours
            "status": "detected",
            "actions_taken": [],
        }
        self._breach_log.append(breach)
        logger.critical("DATA BREACH DETECTED: %s (affects %d records)", description, affected_records)
        return breach

    def get_data_requests(self, status: str = "") -> list[dict]:
        if status:
            return [r for r in self._data_requests if r["status"] == status]
        return self._data_requests

    def get_breach_log(self) -> list[dict]:
        return self._breach_log

    def get_retention_policies(self) -> dict:
        return RETENTION_POLICIES

    def get_purpose_registry(self) -> dict:
        return PURPOSE_REGISTRY


dpdp_manager = DPDPComplianceManager()
