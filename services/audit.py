import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.audit import AuditLog


def _dump(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value[:4000]
    try:
        return json.dumps(value, ensure_ascii=False, default=str)[:4000]
    except TypeError:
        return str(value)[:4000]


async def write_audit(
    db: AsyncSession,
    *,
    admin=None,
    action: str,
    resource: str,
    resource_id: str | None = None,
    old_value: Any = None,
    new_value: Any = None,
    ip_address: str | None = None,
) -> None:
    db.add(AuditLog(
        admin_id=getattr(admin, "id", None),
        admin_username=getattr(admin, "username", None),
        action=action,
        resource=resource,
        resource_id=resource_id,
        old_value=_dump(old_value),
        new_value=_dump(new_value),
        ip_address=ip_address,
    ))
    await db.flush()
