"""Tests for CamelCaseModel."""

import json

from safir.pydantic import CamelCaseModel, to_camel_case


def test_to_camel_case() -> None:
    assert to_camel_case("foo") == "foo"
    assert to_camel_case("minimum_lifetime") == "minimumLifetime"
    assert to_camel_case("replace_403") == "replace403"
    assert to_camel_case("foo_bar_baz") == "fooBarBaz"


def test_camel_case_model() -> None:
    class TestModel(CamelCaseModel):
        minimum_lifetime: int
        replace_403: bool
        foo_bar_baz: str

    camel = {
        "minimumLifetime": 10,
        "replace403": False,
        "fooBarBaz": "something",
    }
    snake = {
        "minimum_lifetime": 10,
        "replace_403": False,
        "foo_bar_baz": "something",
    }
    data = TestModel.model_validate(camel)
    assert data.minimum_lifetime == 10
    assert not data.replace_403
    assert data.foo_bar_baz == "something"
    assert data.model_dump() == camel
    assert data.model_dump(by_alias=False) == snake
    assert json.loads(data.model_dump_json()) == camel
    assert json.loads(data.model_dump_json(by_alias=False)) == snake

    snake_data = TestModel.model_validate(snake)
    assert data.minimum_lifetime == 10
    assert not data.replace_403
    assert data.foo_bar_baz == "something"
    assert snake_data.model_dump() == data.model_dump()
    assert snake_data.model_dump_json() == data.model_dump_json()
