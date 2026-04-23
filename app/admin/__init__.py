from app.admin.audit import build_audit_router
from app.admin.deps import require_role
from app.admin.grants import build_grants_router
from app.admin.tools import build_tools_router

__all__ = [
    "build_audit_router",
    "build_grants_router",
    "build_tools_router",
    "require_role",
]
