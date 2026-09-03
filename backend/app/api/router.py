"""Single place every route module is mounted, so main.py stays a thin entry point.

Order matters: `reports` declares literal paths such as /reports/bulk-approve and
/reports/export/unpaid.csv, and is mounted before the modules that add /reports/{id}/...
sub-resources.
"""

from fastapi import APIRouter

from app.api.routes import (
    alerts,
    approvers,
    auth,
    dashboard,
    health,
    history,
    lines,
    reports,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(reports.router)
api_router.include_router(lines.router)
api_router.include_router(approvers.router)
api_router.include_router(history.router)
api_router.include_router(dashboard.router)
api_router.include_router(alerts.router)
