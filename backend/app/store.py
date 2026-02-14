from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, create_engine, desc, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .models import AuditResult, AuditStatus, ChecklistItem, Issue, Project, Recommendation, ScheduledAudit, User


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./seo_analyzer.db")


class Base(DeclarativeBase):
    pass


class ProjectEntity(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    notify_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)


class UserEntity(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)


class AuditEntity(Base):
    __tablename__ = "audits"

    audit_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    issues: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    recommendations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    checklist: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    metrics: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class ScheduledAuditEntity(Base):
    __tablename__ = "scheduled_audits"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    hour_utc: Mapped[int] = mapped_column(Integer, nullable=False)
    minute_utc: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)


class AuditHistoryEntity(Base):
    __tablename__ = "audit_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)


if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("audits")}
    if "checklist" not in columns:
        with engine.begin() as connection:
            dialect = engine.dialect.name
            if dialect == "sqlite":
                connection.execute(text("ALTER TABLE audits ADD COLUMN checklist JSON"))
                connection.execute(text("UPDATE audits SET checklist = '[]' WHERE checklist IS NULL"))
            else:
                connection.execute(text("ALTER TABLE audits ADD COLUMN checklist JSON"))
                connection.execute(text("UPDATE audits SET checklist = '[]' WHERE checklist IS NULL"))


def _to_audit_model(entity: AuditEntity) -> AuditResult:
    issues = [Issue.model_validate(item) for item in (entity.issues or [])]
    recommendations = [Recommendation.model_validate(item) for item in (entity.recommendations or [])]
    checklist = [ChecklistItem.model_validate(item) for item in (entity.checklist or [])]
    return AuditResult(
        audit_id=entity.audit_id,
        project_id=entity.project_id,
        url=entity.url,
        status=entity.status,
        score=entity.score,
        created_at=entity.created_at,
        finished_at=entity.finished_at,
        issues=issues,
        recommendations=recommendations,
        checklist=checklist,
        metrics=entity.metrics or {},
        error=entity.error,
    )


def _to_schedule_model(entity: ScheduledAuditEntity) -> ScheduledAudit:
    return ScheduledAudit(
        id=entity.id,
        project_id=entity.project_id,
        user_id=entity.user_id,
        url=entity.url,
        weekday=entity.weekday,
        hour_utc=entity.hour_utc,
        minute_utc=entity.minute_utc,
        enabled=bool(entity.enabled),
        last_run_at=entity.last_run_at,
        created_at=entity.created_at,
    )


class DataStore:
    def __init__(self) -> None:
        self.session_factory = SessionLocal

    def _session(self) -> Session:
        return self.session_factory()

    def create_user(self, user: User, password_hash: str) -> User:
        with self._session() as session:
            entity = UserEntity(
                id=user.id,
                email=str(user.email),
                password_hash=password_hash,
                created_at=user.created_at,
            )
            session.add(entity)
            session.commit()
        return user

    def get_user_by_email(self, email: str) -> dict[str, str] | None:
        with self._session() as session:
            row = session.execute(select(UserEntity).where(UserEntity.email == email)).scalar_one_or_none()
            if row is None:
                return None
            return {"id": row.id, "email": row.email, "password_hash": row.password_hash}

    def create_project(self, project: Project) -> Project:
        with self._session() as session:
            entity = ProjectEntity(
                id=project.id,
                user_id=project.user_id,
                name=project.name,
                base_url=project.base_url,
                notify_email=project.notify_email,
                created_at=project.created_at,
            )
            session.add(entity)
            session.commit()
        return project

    def project_exists(self, project_id: str, user_id: str) -> bool:
        with self._session() as session:
            found = session.execute(
                select(ProjectEntity).where(ProjectEntity.id == project_id, ProjectEntity.user_id == user_id)
            ).scalar_one_or_none()
        return found is not None

    def get_project_notify_email(self, project_id: str, user_id: str | None = None) -> str | None:
        with self._session() as session:
            if user_id is None:
                row = session.execute(select(ProjectEntity).where(ProjectEntity.id == project_id)).scalar_one_or_none()
            else:
                row = session.execute(
                    select(ProjectEntity).where(ProjectEntity.id == project_id, ProjectEntity.user_id == user_id)
                ).scalar_one_or_none()
            if row is None:
                return None
            return row.notify_email

    def create_audit(self, audit: AuditResult) -> AuditResult:
        with self._session() as session:
            entity = AuditEntity(
                audit_id=audit.audit_id,
                project_id=audit.project_id,
                url=audit.url,
                status=audit.status,
                score=audit.score,
                created_at=audit.created_at,
                finished_at=audit.finished_at,
                issues=[item.model_dump() for item in audit.issues],
                recommendations=[item.model_dump() for item in audit.recommendations],
                checklist=[item.model_dump() for item in audit.checklist],
                metrics=audit.metrics,
                error=audit.error,
            )
            session.add(entity)
            session.commit()
        return audit

    def get_audit(self, audit_id: str) -> AuditResult | None:
        with self._session() as session:
            entity = session.get(AuditEntity, audit_id)
            if entity is None:
                return None
            return _to_audit_model(entity)

    def get_audit_for_user(self, audit_id: str, user_id: str) -> AuditResult | None:
        with self._session() as session:
            entity = session.execute(
                select(AuditEntity)
                .join(ProjectEntity, ProjectEntity.id == AuditEntity.project_id)
                .where(AuditEntity.audit_id == audit_id, ProjectEntity.user_id == user_id)
            ).scalar_one_or_none()
            if entity is None:
                return None
            return _to_audit_model(entity)

    def set_audit_status(self, audit_id: str, status: AuditStatus, error: str | None = None) -> None:
        with self._session() as session:
            entity = session.get(AuditEntity, audit_id)
            if entity is None:
                return
            entity.status = status
            entity.error = error
            session.commit()

    def complete_audit(self, audit: AuditResult) -> None:
        with self._session() as session:
            entity = session.get(AuditEntity, audit.audit_id)
            if entity is None:
                return
            entity.status = audit.status
            entity.score = audit.score
            entity.finished_at = audit.finished_at
            entity.issues = [item.model_dump() for item in audit.issues]
            entity.recommendations = [item.model_dump() for item in audit.recommendations]
            entity.checklist = [item.model_dump() for item in audit.checklist]
            entity.metrics = audit.metrics
            entity.error = audit.error

            if audit.status == "completed" and audit.score is not None and audit.finished_at is not None:
                session.add(
                    AuditHistoryEntity(
                        project_id=audit.project_id,
                        timestamp=audit.finished_at,
                        score=audit.score,
                    )
                )

            session.commit()

    def get_project_history(self, project_id: str) -> list[dict[str, str | int]]:
        with self._session() as session:
            rows = session.execute(
                select(AuditHistoryEntity)
                .where(AuditHistoryEntity.project_id == project_id)
                .order_by(AuditHistoryEntity.timestamp.asc())
            ).scalars()
            return [{"timestamp": item.timestamp.isoformat(), "score": item.score} for item in rows]

    def get_project_history_for_user(self, project_id: str, user_id: str) -> list[dict[str, str | int]]:
        with self._session() as session:
            rows = session.execute(
                select(AuditHistoryEntity)
                .join(ProjectEntity, ProjectEntity.id == AuditHistoryEntity.project_id)
                .where(AuditHistoryEntity.project_id == project_id, ProjectEntity.user_id == user_id)
                .order_by(AuditHistoryEntity.timestamp.asc())
            ).scalars()
            return [{"timestamp": item.timestamp.isoformat(), "score": item.score} for item in rows]

    def get_project_actions(self, project_id: str) -> list[Recommendation]:
        with self._session() as session:
            latest = session.execute(
                select(AuditEntity)
                .where(AuditEntity.project_id == project_id, AuditEntity.status == "completed")
                .order_by(desc(AuditEntity.finished_at), desc(AuditEntity.created_at))
                .limit(1)
            ).scalar_one_or_none()

            if latest is None:
                return []

            return [Recommendation.model_validate(item) for item in (latest.recommendations or [])]

    def get_project_actions_for_user(self, project_id: str, user_id: str) -> list[Recommendation]:
        with self._session() as session:
            latest = session.execute(
                select(AuditEntity)
                .join(ProjectEntity, ProjectEntity.id == AuditEntity.project_id)
                .where(
                    AuditEntity.project_id == project_id,
                    AuditEntity.status == "completed",
                    ProjectEntity.user_id == user_id,
                )
                .order_by(desc(AuditEntity.finished_at), desc(AuditEntity.created_at))
                .limit(1)
            ).scalar_one_or_none()

            if latest is None:
                return []

            return [Recommendation.model_validate(item) for item in (latest.recommendations or [])]

    def create_schedule(self, schedule: ScheduledAudit) -> ScheduledAudit:
        with self._session() as session:
            row = ScheduledAuditEntity(
                id=schedule.id,
                project_id=schedule.project_id,
                user_id=schedule.user_id,
                url=schedule.url,
                weekday=schedule.weekday,
                hour_utc=schedule.hour_utc,
                minute_utc=schedule.minute_utc,
                enabled=1 if schedule.enabled else 0,
                last_run_at=schedule.last_run_at,
                created_at=schedule.created_at,
            )
            session.add(row)
            session.commit()
        return schedule

    def list_schedules_for_user(self, user_id: str) -> list[ScheduledAudit]:
        with self._session() as session:
            rows = session.execute(
                select(ScheduledAuditEntity)
                .where(ScheduledAuditEntity.user_id == user_id)
                .order_by(desc(ScheduledAuditEntity.created_at))
            ).scalars()
            return [_to_schedule_model(item) for item in rows]

    def due_schedules(self, now_utc: datetime) -> list[ScheduledAudit]:
        with self._session() as session:
            rows = session.execute(select(ScheduledAuditEntity).where(ScheduledAuditEntity.enabled == 1)).scalars().all()
            due: list[ScheduledAudit] = []
            for row in rows:
                if row.weekday != now_utc.weekday():
                    continue
                if row.hour_utc != now_utc.hour or row.minute_utc != now_utc.minute:
                    continue
                if row.last_run_at is not None and now_utc - row.last_run_at < timedelta(days=6):
                    continue
                due.append(_to_schedule_model(row))
            return due

    def mark_schedule_run(self, schedule_id: str, when_utc: datetime) -> None:
        with self._session() as session:
            row = session.get(ScheduledAuditEntity, schedule_id)
            if row is None:
                return
            row.last_run_at = when_utc
            session.commit()

    def get_admin_users_overview(self) -> list[dict[str, object]]:
        with self._session() as session:
            users = session.execute(select(UserEntity).order_by(desc(UserEntity.created_at))).scalars().all()
            results: list[dict[str, object]] = []

            for user in users:
                projects = session.execute(select(ProjectEntity).where(ProjectEntity.user_id == user.id)).scalars().all()
                project_ids = [item.id for item in projects]

                audits: list[AuditEntity] = []
                if project_ids:
                    audits = (
                        session.execute(
                            select(AuditEntity)
                            .where(AuditEntity.project_id.in_(project_ids))
                            .order_by(desc(AuditEntity.created_at))
                        )
                        .scalars()
                        .all()
                    )

                page_stats: dict[str, dict[str, object]] = {}
                scored_audits = [audit for audit in audits if audit.score is not None]

                for audit in audits:
                    stats = page_stats.get(audit.url)
                    if stats is None:
                        stats = {
                            "url": audit.url,
                            "audits_count": 0,
                            "last_status": audit.status,
                            "last_score": audit.score,
                            "last_audit_at": audit.created_at.isoformat(),
                        }
                        page_stats[audit.url] = stats

                    stats["audits_count"] = int(stats["audits_count"]) + 1

                    last_time = datetime.fromisoformat(str(stats["last_audit_at"]))
                    if audit.created_at > last_time:
                        stats["last_status"] = audit.status
                        stats["last_score"] = audit.score
                        stats["last_audit_at"] = audit.created_at.isoformat()

                pages_checked = sorted(
                    page_stats.values(),
                    key=lambda item: str(item["last_audit_at"]),
                    reverse=True,
                )[:8]

                last_audit_at = audits[0].created_at.isoformat() if audits else None
                average_score = round(sum(audit.score or 0 for audit in scored_audits) / len(scored_audits), 2) if scored_audits else None

                results.append(
                    {
                        "user_id": user.id,
                        "email": user.email,
                        "created_at": user.created_at.isoformat(),
                        "projects_count": len(projects),
                        "audits_count": len(audits),
                        "last_audit_at": last_audit_at,
                        "average_score": average_score,
                        "pages_checked": pages_checked,
                    }
                )

            return results
