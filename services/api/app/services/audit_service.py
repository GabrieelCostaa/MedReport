"""
LGPD Audit Trail Service.

Logs all data access and modifications for compliance with:
- LGPD Art. 37: Controller must demonstrate compliance
- LGPD Art. 11: Health data requires explicit legal basis
- ANS RN 501/2022: TISS audit trail requirements
"""
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, AuditAction

logger = logging.getLogger(__name__)


async def audit_log(
    db: AsyncSession,
    action: AuditAction,
    resource_type: str,
    resource_id: Optional[str] = None,
    user_id: Optional[str] = None,
    user_crm: Optional[str] = None,
    user_ip: Optional[str] = None,
    changes: Optional[dict] = None,
    justification: Optional[str] = None,
    metadata: Optional[dict] = None,
):
    """Log an audit event. Fire-and-forget — never blocks the main flow."""
    try:
        entry = AuditLog(
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            user_id=user_id,
            user_crm=user_crm,
            user_ip=user_ip,
            changes=changes,
            justification=justification,
            metadata_=metadata,
        )
        db.add(entry)
        await db.flush()
    except Exception as e:
        logger.warning("Audit log failed (non-blocking): %s", e)
