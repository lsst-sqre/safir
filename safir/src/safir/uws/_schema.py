"""SQLAlchemy schema for the UWS database."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from vo_models.uws.types import ErrorType, ExecutionPhase

from ._models import ErrorCode

__all__ = [
    "Job",
    "JobParameter",
    "JobResult",
    "UWSSchemaBase",
]


class UWSSchemaBase(DeclarativeBase):
    """SQLAlchemy declarative base for the UWS database schema."""


class JobResult(UWSSchemaBase):
    """Table holding job results."""

    __tablename__ = "job_result"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("job.id", ondelete="CASCADE")
    )
    result_id: Mapped[str] = mapped_column(String(64))
    sequence: Mapped[int]
    url: Mapped[str] = mapped_column(String(256))
    size: Mapped[int | None]
    mime_type: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        Index("by_sequence", "job_id", "sequence", unique=True),
        Index("by_result_id", "job_id", "result_id", unique=True),
    )


class JobParameter(UWSSchemaBase):
    """Table holding parameters to UWS jobs."""

    __tablename__ = "job_parameter"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("job.id", ondelete="CASCADE")
    )
    parameter: Mapped[str] = mapped_column(String(64))
    value: Mapped[str] = mapped_column(Text)
    is_post: Mapped[bool] = mapped_column(default=False)

    __table_args__ = (Index("by_parameter", "job_id", "parameter"),)


class Job(UWSSchemaBase):
    """Table holding UWS jobs.

    Notes
    -----
    The details of how the relationships are defined are chosen to allow this
    schema to be used with async SQLAlchemy. Review the SQLAlchemy asyncio
    documentation carefully before making changes. There are a lot of
    surprises and sharp edges.
    """

    __tablename__ = "job"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    message_id: Mapped[str | None] = mapped_column(String(64))
    owner: Mapped[str] = mapped_column(String(64))
    phase: Mapped[ExecutionPhase]
    run_id: Mapped[str | None] = mapped_column(String(64))
    creation_time: Mapped[datetime]
    start_time: Mapped[datetime | None]
    end_time: Mapped[datetime | None]
    destruction_time: Mapped[datetime]
    execution_duration: Mapped[int]
    quote: Mapped[datetime | None]
    error_type: Mapped[ErrorType | None]
    error_code: Mapped[ErrorCode | None]
    error_message: Mapped[str | None] = mapped_column(Text)
    error_detail: Mapped[str | None] = mapped_column(Text)

    parameters: Mapped[list[JobParameter]] = relationship(
        cascade="delete", lazy="selectin", uselist=True
    )
    results: Mapped[list[JobResult]] = relationship(
        cascade="delete", lazy="selectin", uselist=True
    )

    __table_args__ = (
        Index("by_owner_phase", "owner", "phase", "creation_time"),
        Index("by_owner_time", "owner", "creation_time"),
    )
