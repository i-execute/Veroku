from veroku.utils import (
    get_args_raw, get_args, chunks, mention, peer_from_chat,
    chat_from_peer, is_user_peer, fmt_time, rand_id, sanitize_html,
)


class FakeMsg:
    text = ".vkcall kill abc123"
    def __init__(self, text=None):
        if text is not None:
            self.text = text


def test_get_args_raw():
    assert get_args_raw(FakeMsg()) == "kill abc123"
    assert get_args_raw(FakeMsg(".cmd")) == ""
    assert get_args_raw(FakeMsg(".cmd a b c")) == "a b c"


def test_get_args():
    assert get_args(FakeMsg()) == ["kill", "abc123"]
    assert get_args(FakeMsg(".cmd")) == []


def test_chunks():
    assert chunks("abcdefgh", 3) == ["abc", "def", "gh"]
    assert chunks("", 3) == []
    assert all(len(c) <= 3 for c in chunks("x" * 10, 3))


def test_mention():
    assert mention(42, "Bob") == "[id42|Bob]"
    assert mention(42) == "[id42|42]"


def test_peer_chat_conversion():
    assert peer_from_chat(7) == 2000000007
    assert chat_from_peer(2000000007) == 7
    assert chat_from_peer(12345) is None
    assert is_user_peer(12345)
    assert not is_user_peer(2000000007)


def test_fmt_time():
    assert fmt_time(65) == "1m 5s"
    assert fmt_time(3600) == "1h 0m 0s"
    assert fmt_time(86400) == "1d 0h 0m 0s"


def test_rand_id():
    import veroku.utils as u
    orig = u.time.time
    clock = [orig()]
    u.time.time = lambda: clock.__setitem__(0, clock[0] + 1) or clock[0]
    try:
        a, b = rand_id(), rand_id()
    finally:
        u.time.time = orig
    assert a != b and 0 < a < 2**31


def test_sanitize_html():
    assert sanitize_html("<b>&") == "&lt;b&gt;&amp;"
