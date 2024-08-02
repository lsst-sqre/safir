"""The job_parameter database table."""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)

from ._base import UWSSchemaBase

__all__ = ["JobParameter"]


class JobParameter(UWSSchemaBase):
    """Table holding parameters to UWS jobs."""

    __tablename__ = "job_parameter"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    job_id: int = Column(
        Integer, ForeignKey("job.id", ondelete="CASCADE"), nullable=False
    )
    parameter: str = Column(String(64), nullable=False)
    value: str = Column(Text, nullable=False)
    is_post: bool = Column(Boolean, nullable=False, default=False)

    __table_args__ = (Index("by_parameter", "job_id", "parameter"),)
