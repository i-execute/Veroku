import pytest

from veroku.utils import (
    get_args,
    get_args_raw,
    get_args_split,
    rand,
    get_platform,
    get_uptime_string,
    array_sum,
    chunks,
    get_version_raw,
)
from veroku.utils.placeholders import (
    custom_placeholders,
    register_placeholder,
    unregister_placeholders,
    config_placeholders,
)


class FakeMsg:
    def __init__(self, text):
        self.text = text


def test_get_args_raw():
    assert get_args_raw(FakeMsg(".help")) == ""
    assert get_args_raw(FakeMsg(".help me")) == "me"
    assert get_args_raw(FakeMsg("")) == ""


def test_get_args():
    assert get_args(FakeMsg('.ping a "b c"')) == ["a", "b c"]
    assert get_args(FakeMsg(".ping")) == []
    assert get_args(FakeMsg(".ping 'unbalanced")) == ["'unbalanced"]


def test_get_args_split():
    assert get_args_split(FakeMsg(".a b c")) == ["b", "c"]
    assert get_args_split(FakeMsg(".a"), 1) == []


def test_rand():
    assert len(rand(16)) == 16
    assert rand(8) != rand(8)


def test_platform():
    assert get_platform() != ""


def test_uptime_string():
    import time

    assert "s" in get_uptime_string(time.time() - 5)
    assert "1m" in get_uptime_string(time.time() - 65)


def test_array_sum():
    assert array_sum([[1, 2], [3]]) == [1, 2, 3]


def test_chunks():
    assert chunks([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]


def test_version():
    assert get_version_raw().count(".") == 2


def test_placeholders():
    custom_placeholders.clear()

    class FakeInner:
        strings = {"name": "Fake"}

        async def cb(self, _):
            return "value"

    inner = FakeInner()
    register_placeholder("test_ph", inner.cb, "test desc")
    assert "test_ph" in custom_placeholders
    assert config_placeholders() == ["{test_ph} - test desc"]
    assert unregister_placeholders("FakeInner") == 1
    assert custom_placeholders == {}
    custom_placeholders.clear()
