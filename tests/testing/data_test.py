"""Tests for test data handling."""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import ANY

import pytest
from pydantic import BaseModel

from safir.datetime import format_datetime_for_logging
from safir.testing.data import Data


def test_json(tmp_path: Path) -> None:
    data = Data(tmp_path)
    expected = {"foo": "bar", "baz": "two"}
    data.write_json(expected, "some-data")
    assert data.read_json("some-data") == expected
    data.assert_json_matches(expected, "some-data")
    with pytest.raises(AssertionError):
        data.assert_json_matches({"foo": "bar"}, "some-data")


def test_json_update(tmp_path: Path) -> None:
    data = Data(tmp_path, update_test_data=True)
    assert not (tmp_path / "some-data.json").exists()
    data.assert_json_matches({"foo": "bar"}, "some-data")
    with (tmp_path / "some-data.json").open("r") as f:
        assert json.load(f) == {"foo": "bar"}


def test_json_wildcard(tmp_path: Path) -> None:
    data = Data(tmp_path)
    data.write_json({"timestamp": "<ANY>"}, "some-data")
    now = format_datetime_for_logging(datetime.now(tz=UTC))
    data.assert_json_matches({"timestamp": now}, "some-data")
    expected = data.read_json("some-data")
    assert type(expected["timestamp"]) is type(ANY)

    # Test preserving wildcards when updating the data.
    data.write_json({"timestamp": "foo"}, "some-data")
    data.assert_json_matches({"timestamp": now}, "some-data")
    expected = data.read_json("some-data")
    assert type(expected["timestamp"]) is type(ANY)


def test_json_wildcard_nested(tmp_path: Path) -> None:
    """Test wildcard preservation in tested data structures."""
    data = Data(tmp_path, update_test_data=True)
    expected = {
        "foo": {"bar": "baz", "wildcard": "<ANY>"},
        "list": [1, "<ANY>"],
        "short": [1, 2, "<ANY>"],
    }
    data.write_json(expected, "some-data")
    seen = {
        "foo": {"wildcard": "foo", "new": "bar"},
        "list": [0, 1, 2],
        "short": [1],
    }
    data.assert_json_matches(seen, "some-data")
    new = data.read_json("some-data")
    assert new == {
        "foo": {"wildcard": ANY, "new": "bar"},
        "list": [0, ANY, 2],
        "short": [1],
    }
    assert type(new["foo"]["wildcard"]) is type(ANY)
    assert type(new["list"][1]) is type(ANY)


class Model(BaseModel):
    """Small model for Pydantic testing."""

    foo: int
    bar: str


def test_pydantic(tmp_path: Path) -> None:
    data = Data(tmp_path)
    model = Model(foo=4, bar="something")
    data.write_pydantic(model, "model")
    expected = data.read_pydantic(Model, "model")
    assert isinstance(expected, Model)
    assert expected == model
    data.assert_pydantic_matches(model, "model")
    model.foo = 5
    with pytest.raises(AssertionError):
        data.assert_pydantic_matches(model, "model")


def test_pydantic_update(tmp_path: Path) -> None:
    data = Data(tmp_path, update_test_data=True)
    model = Model(foo=4, bar="something")
    assert not (tmp_path / "model.json").exists()
    data.assert_pydantic_matches(model, "model")
    model_json = data.read_json("model")
    assert model_json == {"foo": 4, "bar": "something"}
    expected = data.read_pydantic(Model, "model")
    assert isinstance(expected, Model)
    assert model == expected


def test_text(tmp_path: Path) -> None:
    (tmp_path / "foo").mkdir()
    data = Data(tmp_path)
    data.write_text("some\ntest data", "foo/data")
    assert data.read_text("foo/data") == "some\ntest data"
    data.assert_text_matches("some\ntest data", "foo/data")
    with pytest.raises(AssertionError):
        data.assert_text_matches("some\ntest data\n", "foo/data")


def test_text_update(tmp_path: Path) -> None:
    data = Data(tmp_path, update_test_data=True)
    assert not (tmp_path / "test-data").exists()
    data.assert_text_matches("some\ntest data", "test-data")
    assert (tmp_path / "test-data").read_text() == "some\ntest data"
