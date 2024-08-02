"""The job database table.

The details of how the relationships are defined are chosen to allow this
schema to be used with async SQLAlchemy. Review the SQLAlchemy asyncio
documentation carefully before making changes. There are a lot of surprises
and sharp edges.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from sqlalchemy import Column, DateTime, Enum, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, relationship
from vo_models.uws.types import ErrorType, ExecutionPhase

from .._models import ErrorCode
from ._base import UWSSchemaBase
from ._job_parameter import JobParameter
from ._job_result import JobResult

__all__ = ["Job"]


class Job(UWSSchemaBase):
    """Table holding UWS jobs."""

    __tablename__ = "job"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    message_id: str | None = Column(String(64))
    owner: str = Column(String(64), nullable=False)
    phase: ExecutionPhase = Column(Enum(ExecutionPhase), nullable=False)
    run_id: str | None = Column(String(64))
    creation_time: datetime = Column(DateTime, nullable=False)
    start_time: datetime | None = Column(DateTime)
    end_time: datetime | None = Column(DateTime)
    destruction_time: datetime = Column(DateTime, nullable=False)
    execution_duration: int = Column(Integer, nullable=False)
    quote: datetime | None = Column(DateTime)
    error_type: ErrorType | None = Column(Enum(ErrorType))
    error_code: ErrorCode | None = Column(Enum(ErrorCode))
    error_message: str | None = Column(Text)
    error_detail: str | None = Column(Text)

    parameters: Mapped[list[JobParameter]] = relationship(
        cascade="delete", lazy="selectin", uselist=True
    )
    results: Mapped[list[JobResult]] = relationship(
        cascade="delete", lazy="selectin", uselist=True
    )

    __mapper_args__: ClassVar[dict[str, bool]] = {"eager_defaults": True}
    __table_args__ = (
        Index("by_owner_phase", "owner", "phase", "creation_time"),
        Index("by_owner_time", "owner", "creation_time"),
    )
