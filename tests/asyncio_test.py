"""Tests for asyncio utility functions."""

from __future__ import annotations

from safir.asyncio import run_with_asyncio


def test_run_with_asyncio() -> None:
    @run_with_asyncio
    async def some_async_function() -> str:
        return "some result"

    assert some_async_function() == "some result"
