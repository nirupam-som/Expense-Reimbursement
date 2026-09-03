"""Enumerations stored as native PostgreSQL enum types.

Kept in one module so models, schemas and services all agree on the same values, and so
an illegal value is rejected by the database regardless of which code path writes it.
"""

import enum


class UserRole(str, enum.Enum):
    employee = "employee"
    approver = "approver"


class ReportStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"
    paid = "paid"


class ExpenseCategory(str, enum.Enum):
    travel = "travel"
    lodging = "lodging"
    meals = "meals"
    transportation = "transportation"
    supplies = "supplies"
    other = "other"
