import pytest

from tests.fixtures.helpers import get_bound_tcp_port


class _DummySiteNoAttrs:
    pass


class _DummySocket:
    def __init__(self, port: int) -> None:
        self._port = port

    def getsockname(self):
        return ("127.0.0.1", self._port)


class _DummyServer:
    def __init__(self, port: int) -> None:
        self.sockets = [_DummySocket(port)]


class _DummySiteWithName:
    def __init__(self, port: int) -> None:
        self.name = f"http://localhost:{port}"


class _DummySiteWithServer:
    def __init__(self, port: int) -> None:
        self._server = _DummyServer(port)


def test_get_bound_tcp_port_raises_on_unresolvable_site():
    with pytest.raises(RuntimeError, match="Unable to resolve bound TCP port"):
        get_bound_tcp_port(_DummySiteNoAttrs())


def test_get_bound_tcp_port_uses_name_port_when_available():
    assert get_bound_tcp_port(_DummySiteWithName(8081)) == 8081


def test_get_bound_tcp_port_falls_back_to_server_sockets():
    assert get_bound_tcp_port(_DummySiteWithServer(9092)) == 9092
