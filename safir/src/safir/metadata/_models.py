"""Standardized metadata models."""

from __future__ import annotations

from pydantic import BaseModel, Field

__all__ = ["Metadata"]


class Metadata(BaseModel):
    """Metadata about a package."""

    name: str = Field(..., title="Application name", examples=["myapp"])

    version: str = Field(..., title="Version", examples=["1.0.0"])

    description: str | None = Field(
        None, title="Description", examples=["Some package description"]
    )

    repository_url: str | None = Field(
        None, title="Repository URL", examples=["https://example.com/"]
    )

    documentation_url: str | None = Field(
        None, title="Documentation URL", examples=["https://example.com/"]
    )
