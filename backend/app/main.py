from __future__ import annotations

from io import BytesIO
import os
import smtplib
import threading
import time
import hashlib
import hmac
import base64
from datetime import datetime
from email.message import EmailMessage
from urllib.parse import urlparse
from uuid import uuid4
from typing import Literal

import jwt
from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis import Redis
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from rq import Queue

from .models import (
    AuditResult,
    AuditStatusResponse,
    ChecklistItem,
    CreateProjectRequest,
    LoginRequest,
    Project,
    Recommendation,
    RegisterUserRequest,
    ScheduledAudit,
    ScheduleAuditRequest,
    StartAuditRequest,
    TokenResponse,
    User,
)
from .seo_checks import (
    build_issues,
    calculate_score,
    fetch_page,
    run_lighthouse_audit,
    run_playwright_audit,
)
from .store import DataStore, init_db


app = FastAPI(title="SEO Analyzer API", version="0.1.0")
store = DataStore()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = Redis.from_url(REDIS_URL)
audit_queue = Queue("audits", connection=redis_client)

JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))
security = HTTPBearer(auto_error=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def to_recommendations(audit: AuditResult) -> list[Recommendation]:
    recommendations: list[Recommendation] = []
    for issue in sorted(audit.issues, key=lambda item: item.priority_score, reverse=True):
        if issue.priority_score >= 2.0:
            bucket = "do_now"
        elif issue.priority_score >= 1.0:
            bucket = "this_week"
        else:
            bucket = "later"

        recommendations.append(
            Recommendation(
                title=issue.title,
                reason=issue.details,
                action=issue.fix_suggestion,
                bucket=bucket,
                priority_score=issue.priority_score,
            )
        )
    return recommendations


def build_top20_checklist(audit: AuditResult) -> list[ChecklistItem]:
    metrics = audit.metrics
    parsed = urlparse(audit.url)
    clean_url = "?" not in audit.url and len(parsed.path) <= 75

    lcp = metrics.get("lighthouse_lcp_ms")
    cls = metrics.get("lighthouse_cls")
    tbt = metrics.get("lighthouse_tbt_ms")
    lighthouse_seo = metrics.get("lighthouse_seo_score")

    def optional_checklist_item(
        *,
        key: str,
        label: str,
        target: str,
        value: float | None,
        threshold_check: bool,
        format_value: str,
        priority: Literal["do_now", "this_week", "later"],
    ) -> ChecklistItem:
        if value is None:
            return ChecklistItem(
                key=key,
                label=label,
                target=target,
                value="n/a (nepamatuota)",
                passed=True,
                priority="later",
            )

        return ChecklistItem(
            key=key,
            label=label,
            target=target,
            value=format_value,
            passed=threshold_check,
            priority=priority,
        )

    items: list[ChecklistItem] = [
        ChecklistItem(key="http_200", label="HTTP status is 200", target="status = 200", value=str(int(metrics.get("status_code", 0))), passed=metrics.get("status_code", 0) == 200, priority="do_now"),
        ChecklistItem(key="indexable", label="Page is indexable", target="no noindex", value=str(int(metrics.get("noindex_detected", 0))), passed=metrics.get("noindex_detected", 0) == 0, priority="do_now"),
        ChecklistItem(key="robots", label="robots.txt does not block all", target="disallow_all = 0", value=str(int(metrics.get("robots_disallow_all", 0))), passed=metrics.get("robots_disallow_all", 0) == 0, priority="do_now"),
        ChecklistItem(key="canonical", label="Canonical tag exists", target="present = 1", value=str(int(metrics.get("canonical_present", 0))), passed=metrics.get("canonical_present", 0) == 1, priority="this_week"),
        ChecklistItem(key="title_len", label="Title length", target="50-60", value=str(int(metrics.get("title_length", 0))), passed=50 <= metrics.get("title_length", 0) <= 60, priority="this_week"),
        ChecklistItem(key="meta_len", label="Meta description length", target="140-160", value=str(int(metrics.get("meta_description_length", 0))), passed=140 <= metrics.get("meta_description_length", 0) <= 160, priority="this_week"),
        ChecklistItem(key="clean_url", label="Clean URL slug", target="<=75 chars, no query", value=parsed.path or "/", passed=clean_url, priority="later"),
        ChecklistItem(key="single_h1", label="Single H1", target="exactly 1", value=str(int(metrics.get("h1_count", 0))), passed=metrics.get("h1_count", 0) == 1, priority="this_week"),
        ChecklistItem(key="h2_present", label="At least one H2", target=">=1", value=str(int(metrics.get("h2_count", 0))), passed=metrics.get("h2_count", 0) >= 1, priority="later"),
        ChecklistItem(key="content_depth", label="Content depth", target=">=600 words", value=str(int(metrics.get("word_count", 0))), passed=metrics.get("word_count", 0) >= 600, priority="this_week"),
        ChecklistItem(key="internal_links", label="Internal links out", target=">=3", value=str(int(metrics.get("internal_links", 0))), passed=metrics.get("internal_links", 0) >= 3, priority="this_week"),
        ChecklistItem(key="broken_links", label="Broken internal links", target="0", value=str(int(metrics.get("broken_internal_links", 0))), passed=metrics.get("broken_internal_links", 0) == 0, priority="do_now"),
        ChecklistItem(key="https", label="HTTPS enabled", target="1", value=str(int(metrics.get("https_enabled", 0))), passed=metrics.get("https_enabled", 0) == 1, priority="do_now"),
        ChecklistItem(key="mixed_content", label="Mixed content resources", target="0", value=str(int(metrics.get("mixed_content_count", 0))), passed=metrics.get("mixed_content_count", 0) == 0, priority="do_now"),
        ChecklistItem(key="sitemap", label="Sitemap.xml valid", target="present = 1", value=str(int(metrics.get("sitemap_ok", 0))), passed=metrics.get("sitemap_ok", 0) == 1, priority="this_week"),
        optional_checklist_item(
            key="lcp",
            label="LCP",
            target="<=2500 ms",
            value=lcp,
            threshold_check=(lcp is not None and lcp <= 2500),
            format_value=f"{int(lcp)}" if lcp is not None else "",
            priority="do_now",
        ),
        optional_checklist_item(
            key="cls",
            label="CLS",
            target="<=0.10",
            value=cls,
            threshold_check=(cls is not None and cls <= 0.10),
            format_value=f"{cls:.3f}" if cls is not None else "",
            priority="do_now",
        ),
        optional_checklist_item(
            key="tbt",
            label="TBT",
            target="<=200 ms",
            value=tbt,
            threshold_check=(tbt is not None and tbt <= 200),
            format_value=f"{int(tbt)}" if tbt is not None else "",
            priority="this_week",
        ),
        ChecklistItem(key="open_graph", label="Open Graph complete", target="title+description", value=str(int(metrics.get("og_complete", 0))), passed=metrics.get("og_complete", 0) == 1, priority="later"),
        optional_checklist_item(
            key="lh_seo",
            label="Lighthouse SEO",
            target=">=90",
            value=lighthouse_seo,
            threshold_check=(lighthouse_seo is not None and lighthouse_seo >= 90),
            format_value=f"{int(lighthouse_seo)}" if lighthouse_seo is not None else "",
            priority="this_week",
        ),
    ]
    return items


def calculate_hybrid_score(issue_score: int, checklist: list[ChecklistItem]) -> tuple[int, float]:
    measured = [item for item in checklist if "n/a" not in item.value.lower() and "nepamatuota" not in item.value.lower()]
    if not measured:
        return issue_score, float(issue_score)

    checklist_score = (sum(1 for item in measured if item.passed) / len(measured)) * 100
    final_score = round((issue_score * 0.6) + (checklist_score * 0.4))
    return int(final_score), checklist_score


def create_access_token(user_id: str, email: str) -> str:
    expire = datetime.utcnow().timestamp() + (JWT_EXPIRE_HOURS * 3600)
    payload = {"sub": user_id, "email": email, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return f"pbkdf2_sha256${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt_b64, digest_b64 = encoded.split("$", 2)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64.encode())
        expected = base64.b64decode(digest_b64.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, str]:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authorization token")

    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = str(payload.get("sub", ""))
        email = str(payload.get("email", ""))
        if not user_id or not email:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"id": user_id, "email": email}
    except jwt.PyJWTError as error:
        raise HTTPException(status_code=401, detail="Invalid token") from error


def run_audit(audit_id: str) -> None:
    audit = store.get_audit(audit_id)
    if audit is None:
        return

    audit.status = "running"
    store.set_audit_status(audit_id, "running")
    try:
        snapshot = fetch_page(audit.url)
        audit_metrics = {}
        audit_metrics.update(run_playwright_audit(audit.url))
        audit_metrics.update(run_lighthouse_audit(audit.url))

        issues = build_issues(snapshot, audit_metrics=audit_metrics)
        issue_score = calculate_score(issues, snapshot.status_code)

        audit.issues = issues
        audit.metrics = {
            "response_ms": snapshot.response_ms,
            "status_code": float(snapshot.status_code),
            "h1_count": float(snapshot.h1_count),
            "h2_count": float(snapshot.h2_count),
            "images_missing_alt": float(snapshot.image_without_alt),
            "internal_links": float(snapshot.internal_links),
            "broken_internal_links": float(snapshot.broken_internal_links),
            "title_length": float(len(snapshot.title)),
            "meta_description_length": float(len(snapshot.meta_description)),
            "word_count": float(snapshot.word_count),
            "mixed_content_count": float(snapshot.mixed_content_count),
            "hreflang_count": float(snapshot.hreflang_count),
            "invalid_hreflang_count": float(snapshot.invalid_hreflang_count),
            "https_enabled": 1.0 if snapshot.https_enabled else 0.0,
            "canonical_present": 1.0 if snapshot.canonical else 0.0,
            "noindex_detected": 1.0 if "noindex" in snapshot.meta_robots else 0.0,
            "sitemap_ok": 1.0 if snapshot.sitemap_ok else 0.0,
            "robots_disallow_all": 1.0 if snapshot.robots_disallow_all else 0.0,
            "og_complete": 1.0 if snapshot.og_title and snapshot.og_description else 0.0,
        }
        audit.metrics.update(audit_metrics)
        audit.recommendations = to_recommendations(audit)
        audit.checklist = build_top20_checklist(audit)
        score, checklist_score = calculate_hybrid_score(issue_score, audit.checklist)
        audit.score = score
        audit.metrics.update(
            {
                "issue_score": float(issue_score),
                "checklist_score": float(round(checklist_score, 2)),
                "hybrid_score": float(score),
            }
        )
        audit.status = "completed"
        audit.finished_at = datetime.utcnow()
        store.complete_audit(audit)

        notify_email = store.get_project_notify_email(audit.project_id)
        if notify_email:
            send_audit_email(notify_email, audit)
    except Exception as error:
        audit.status = "failed"
        audit.error = str(error)
        audit.finished_at = datetime.utcnow()

        store.complete_audit(audit)


def enqueue_audit_job(audit_id: str) -> None:
    try:
        audit_queue.enqueue(run_audit, audit_id, job_timeout=1200)
    except Exception:
        thread = threading.Thread(target=run_audit, args=(audit_id,), daemon=True)
        thread.start()


def send_audit_email(recipient: str, audit: AuditResult) -> None:
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_sender = os.getenv("SMTP_SENDER", smtp_user)

    if not smtp_host or not smtp_sender:
        return

    pdf_data = build_pdf_report(audit)
    message = EmailMessage()
    message["Subject"] = f"SEO audit completed: {audit.url}"
    message["From"] = smtp_sender
    message["To"] = recipient
    message.set_content(
        f"Audit completed for {audit.url}\n"
        f"Status: {audit.status}\n"
        f"Score: {audit.score if audit.score is not None else '-'}\n"
    )
    message.add_attachment(pdf_data, maintype="application", subtype="pdf", filename=f"seo-audit-{audit.audit_id}.pdf")

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as smtp:
        smtp.starttls()
        if smtp_user:
            smtp.login(smtp_user, smtp_password)
        smtp.send_message(message)


def scheduler_loop() -> None:
    while True:
        now = datetime.utcnow().replace(second=0, microsecond=0)
        try:
            for schedule in store.due_schedules(now):
                audit_id = str(uuid4())
                audit = AuditResult(
                    audit_id=audit_id,
                    project_id=schedule.project_id,
                    url=schedule.url,
                    status="queued",
                    created_at=datetime.utcnow(),
                )
                store.create_audit(audit)
                enqueue_audit_job(audit_id)
                store.mark_schedule_run(schedule.id, now)
        except Exception:
            pass
        time.sleep(30)


def build_pdf_report(audit: AuditResult) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 50
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(40, y, "SEO Audit Report")
    y -= 24

    pdf.setFont("Helvetica", 11)
    pdf.drawString(40, y, f"URL: {audit.url}")
    y -= 16
    pdf.drawString(40, y, f"Status: {audit.status}")
    y -= 16
    pdf.drawString(40, y, f"Score: {audit.score if audit.score is not None else '-'}")
    y -= 16
    pdf.drawString(40, y, f"Report version: 2 | Generated: {datetime.utcnow().isoformat()}Z")
    y -= 28

    checklist = audit.checklist or build_top20_checklist(audit)
    passed = sum(1 for item in checklist if item.passed)

    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(40, y, f"Top 20 SEO checklist ({passed}/20)")
    y -= 18
    pdf.setFont("Helvetica", 10)
    for item in checklist:
        pdf.drawString(42, y, f"- [{'PASS' if item.passed else 'FAIL'}] {item.label} | target: {item.target} | value: {item.value}")
        y -= 14
        if y < 80:
            pdf.showPage()
            y = height - 50
            pdf.setFont("Helvetica", 10)

    y -= 8

    priority_labels = {"do_now": "Dabar", "this_week": "Sia savaite", "later": "Veliau"}
    for bucket in ["do_now", "this_week", "later"]:
        failed = [item for item in checklist if not item.passed and item.priority == bucket][:5]
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(40, y, f"Prioritetas: {priority_labels[bucket]}")
        y -= 16
        pdf.setFont("Helvetica", 10)
        if not failed:
            pdf.drawString(42, y, "- Nera kritiniu neatitikimu")
            y -= 14
        else:
            for item in failed:
                pdf.drawString(42, y, f"- {item.label}: target {item.target}, value {item.value}")
                y -= 14
                if y < 80:
                    pdf.showPage()
                    y = height - 50
                    pdf.setFont("Helvetica", 10)

    y -= 8

    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(40, y, "Top issues")
    y -= 18
    pdf.setFont("Helvetica", 10)

    for issue in audit.issues[:8]:
        line = f"- {issue.title} [{issue.severity}]"
        pdf.drawString(42, y, line[:110])
        y -= 14
        pdf.drawString(52, y, f"Kodel svarbu: {issue.details}"[:110])
        y -= 14
        pdf.drawString(52, y, f"Kaip pataisyti: {issue.fix_suggestion}"[:110])
        y -= 16
        if y < 80:
            pdf.showPage()
            y = height - 50
            pdf.setFont("Helvetica", 10)

    y -= 6
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(40, y, "Action plan")
    y -= 18
    pdf.setFont("Helvetica", 10)
    for item in audit.recommendations[:10]:
        line = f"- ({item.bucket}) {item.title}"
        pdf.drawString(42, y, line[:110])
        y -= 14
        pdf.drawString(52, y, f"Paaiskinimas: {item.reason}"[:110])
        y -= 14
        pdf.drawString(52, y, f"Veiksmas: {item.action}"[:110])
        y -= 14
        if y < 80:
            pdf.showPage()
            y = height - 50
            pdf.setFont("Helvetica", 10)

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


@app.on_event("startup")
def startup_event() -> None:
    init_db()
    thread = threading.Thread(target=scheduler_loop, daemon=True)
    thread.start()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/auth/register", response_model=User)
def register_user(payload: RegisterUserRequest) -> User:
    if store.get_user_by_email(str(payload.email)) is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(id=str(uuid4()), email=payload.email, created_at=datetime.utcnow())
    password_hash = hash_password(payload.password)
    return store.create_user(user, password_hash)


@app.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    found = store.get_user_by_email(str(payload.email))
    if found is None or not verify_password(payload.password, found["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(found["id"], found["email"])
    return TokenResponse(access_token=token)


@app.post("/projects", response_model=Project)
def create_project(payload: CreateProjectRequest, current_user: dict[str, str] = Depends(get_current_user)) -> Project:
    project = Project(
        id=str(uuid4()),
        user_id=current_user["id"],
        name=payload.name,
        base_url=str(payload.base_url),
        notify_email=str(payload.notify_email) if payload.notify_email else None,
        created_at=datetime.utcnow(),
    )
    return store.create_project(project)


@app.post("/audits/start", response_model=AuditStatusResponse)
def start_audit(payload: StartAuditRequest, current_user: dict[str, str] = Depends(get_current_user)) -> AuditStatusResponse:
    if not store.project_exists(payload.project_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="Project not found")

    audit_id = str(uuid4())
    audit = AuditResult(
        audit_id=audit_id,
        project_id=payload.project_id,
        url=str(payload.url),
        status="queued",
        created_at=datetime.utcnow(),
    )
    store.create_audit(audit)
    enqueue_audit_job(audit_id)
    return AuditStatusResponse(audit_id=audit_id, status="queued")


@app.get("/audits/{audit_id}/status", response_model=AuditStatusResponse)
def get_audit_status(audit_id: str, current_user: dict[str, str] = Depends(get_current_user)) -> AuditStatusResponse:
    audit = store.get_audit_for_user(audit_id, current_user["id"])
    if audit is None:
        raise HTTPException(status_code=404, detail="Audit not found")
    return AuditStatusResponse(audit_id=audit_id, status=audit.status)


@app.get("/audits/{audit_id}/results", response_model=AuditResult)
def get_audit_results(audit_id: str, current_user: dict[str, str] = Depends(get_current_user)) -> AuditResult:
    audit = store.get_audit_for_user(audit_id, current_user["id"])
    if audit is None:
        raise HTTPException(status_code=404, detail="Audit not found")
    return audit


@app.get("/projects/{project_id}/history")
def get_project_history(project_id: str, current_user: dict[str, str] = Depends(get_current_user)) -> dict[str, object]:
    if not store.project_exists(project_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="Project not found")

    history = store.get_project_history_for_user(project_id, current_user["id"])
    return {"project_id": project_id, "history": history}


@app.get("/projects/{project_id}/actions")
def get_project_actions(project_id: str, current_user: dict[str, str] = Depends(get_current_user)) -> dict[str, object]:
    if not store.project_exists(project_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="Project not found")

    return {"project_id": project_id, "actions": store.get_project_actions_for_user(project_id, current_user["id"])}


@app.post("/schedules", response_model=ScheduledAudit)
def create_schedule(payload: ScheduleAuditRequest, current_user: dict[str, str] = Depends(get_current_user)) -> ScheduledAudit:
    if not store.project_exists(payload.project_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="Project not found")

    schedule = ScheduledAudit(
        id=str(uuid4()),
        project_id=payload.project_id,
        user_id=current_user["id"],
        url=str(payload.url),
        weekday=payload.weekday,
        hour_utc=payload.hour_utc,
        minute_utc=payload.minute_utc,
        enabled=payload.enabled,
        created_at=datetime.utcnow(),
    )
    return store.create_schedule(schedule)


@app.get("/schedules")
def list_schedules(current_user: dict[str, str] = Depends(get_current_user)) -> dict[str, object]:
    return {"items": store.list_schedules_for_user(current_user["id"])}


@app.get("/audits/{audit_id}/report.pdf")
def get_audit_pdf_report(
    audit_id: str,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    token: str | None = Query(default=None),
) -> Response:
    current_user: dict[str, str]
    if credentials is not None:
        current_user = get_current_user(credentials)
    elif token:
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user_id = str(payload.get("sub", ""))
            email = str(payload.get("email", ""))
            if not user_id or not email:
                raise HTTPException(status_code=401, detail="Invalid token")
            current_user = {"id": user_id, "email": email}
        except jwt.PyJWTError as error:
            raise HTTPException(status_code=401, detail="Invalid token") from error
    else:
        raise HTTPException(status_code=401, detail="Missing authorization token")

    audit = store.get_audit_for_user(audit_id, current_user["id"])
    if audit is None:
        raise HTTPException(status_code=404, detail="Audit not found")
    if audit.status != "completed":
        raise HTTPException(status_code=409, detail="Audit is not completed yet")

    payload = build_pdf_report(audit)
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="seo-audit-{audit_id}.pdf"'},
    )
