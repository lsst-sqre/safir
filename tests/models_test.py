"""Tests for safir.models."""

from __future__ import annotations

import json

from safir.models import ErrorModel


def test_error_model() -> None:
    """Nothing much to test, but make sure the code can be imported."""
    error = {
        "detail": [
            {
                "loc": ["path", "foo"],
                "msg": "Invalid foo",
                "type": "invalid_foo",
            }
        ]
    }
    model = ErrorModel.parse_raw(json.dumps(error))
    assert model.dict() == error
