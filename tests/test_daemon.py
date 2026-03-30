from tq.core.daemon import _pid_alive


def test_pid_alive_false_for_none() -> None:
    assert _pid_alive(None) is False
