from typing import Literal

from pydantic import BaseModel, Field


class BulkDecisionRequest(BaseModel):
    report_ids: list[int] = Field(min_length=1, max_length=200)
    reason: str | None = Field(default=None, max_length=1000)


class BulkItemResult(BaseModel):
    """The outcome for one report in a bulk action.

    `refusal_code` is the machine-readable reason. `owner_is_approver` is the one the
    brief singles out: reports refused specifically because the approver owns them have
    to be distinguishable from every other refusal.
    """

    report_id: int
    outcome: Literal["approved", "rejected", "refused", "not_found"]
    refusal_code: str | None = None
    message: str | None = None


class BulkResultOut(BaseModel):
    results: list[BulkItemResult]
    succeeded: int
    refused: int
    # Called out separately so the UI can say "3 were yours and were skipped" without
    # re-deriving it from the per-report list.
    owned_by_you: int
