from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import ReportStatus
from app.schemas.user import UserSummary


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class TimelineEntryOut(BaseModel):
    """One entry in a report's immutable timeline.

    Status changes and comments are stored in separate tables (they have different
    shapes) but read as one chronological stream, which is how a reader thinks about it.
    """

    kind: Literal["status_change", "comment"]
    id: int
    at: datetime
    actor: UserSummary
    from_status: ReportStatus | None = None
    to_status: ReportStatus | None = None
    reason: str | None = None
    body: str | None = None
