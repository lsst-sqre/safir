"""The job_result database table."""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Index, Integer, String

from ._base import UWSSchemaBase

__all__ = ["JobResult"]


class JobResult(UWSSchemaBase):
    """Table holding job results."""

    __tablename__ = "job_result"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    job_id: int = Column(
        Integer, ForeignKey("job.id", ondelete="CASCADE"), nullable=False
    )
    result_id: str = Column(String(64), nullable=False)
    sequence: int = Column(Integer, nullable=False)
    url: str = Column(String(256), nullable=False)
    size: int | None = Column(Integer)
    mime_type: str | None = Column(String(64))

    __table_args__ = (
        Index("by_sequence", "job_id", "sequence", unique=True),
        Index("by_result_id", "job_id", "result_id", unique=True),
    )
