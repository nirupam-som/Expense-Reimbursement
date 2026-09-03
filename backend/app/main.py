"""FastAPI entry point.

Run locally with:  uvicorn app.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings

app = FastAPI(
    title="Expense Reimbursement API",
    description="Expense reports, approvals and reimbursement tracking.",
    version="0.1.0",
)

# The SPA is served from a different origin (Vercel) than this API (Render), so CORS is
# required. allow_credentials stays False: auth travels in the Authorization header, not
# in cookies, so the browser never needs to send credentials cross-site.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
