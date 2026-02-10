from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, HttpUrl


Severity = Literal["low", "medium", "high", "critical"]
Impact = Literal["low", "medium", "high"]
Effort = Literal["easy", "medium", "hard"]
AuditStatus = Literal["queued", "running", "completed", "failed"]


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    base_url: HttpUrl
    notify_email: EmailStr | None = None


class Project(BaseModel):
    id: str
    user_id: str
    name: str
    base_url: str
    notify_email: str | None = None
    created_at: datetime


class StartAuditRequest(BaseModel):
    project_id: str
    url: HttpUrl


class RegisterUserRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class User(BaseModel):
    id: str
    email: EmailStr
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ScheduleAuditRequest(BaseModel):
    project_id: str
    url: HttpUrl
    weekday: int = Field(ge=0, le=6)
    hour_utc: int = Field(ge=0, le=23)
    minute_utc: int = Field(ge=0, le=59)
    enabled: bool = True


class ScheduledAudit(BaseModel):
    id: str
    project_id: str
    user_id: str
    url: str
    weekday: int
    hour_utc: int
    minute_utc: int
    enabled: bool
    last_run_at: datetime | None = None
    created_at: datetime


class Issue(BaseModel):
    key: str
    title: str
    details: str
    severity: Severity
    impact: Impact
    effort: Effort
    fix_suggestion: str
    confidence: float = Field(ge=0, le=1)
    priority_score: float = Field(ge=0)


class Recommendation(BaseModel):
    title: str
    reason: str
    action: str
    bucket: Literal["do_now", "this_week", "later"]
    priority_score: float


class ChecklistItem(BaseModel):
    key: str
    label: str
    target: str
    value: str
    passed: bool
    priority: Literal["do_now", "this_week", "later"]


class AuditResult(BaseModel):
    audit_id: str
    project_id: str
    url: str
    status: AuditStatus
    score: int | None = None
    created_at: datetime
    finished_at: datetime | None = None
    issues: list[Issue] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    checklist: list[ChecklistItem] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    error: str | None = None


class AuditStatusResponse(BaseModel):
    audit_id: str
    status: AuditStatus
