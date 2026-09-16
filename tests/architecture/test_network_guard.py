import socket

import pytest

from conftest import block_live_network


@pytest.mark.parametrize(
    ("family", "host"),
    [(socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")],
)
def test_numeric_loopback_connects_to_local_listener(family, host):
    try:
        listener = socket.socket(family, socket.SOCK_STREAM)
    except OSError as exc:
        if family == socket.AF_INET6:
            pytest.skip(f"IPv6 unavailable: {exc}")
        raise
    with listener:
        listener.settimeout(2)
        try:
            listener.bind((host, 0))
        except OSError as exc:
            if family == socket.AF_INET6:
                pytest.skip(f"IPv6 loopback unavailable: {exc}")
            raise
        listener.listen(1)
        with socket.socket(family, socket.SOCK_STREAM) as client:
            client.settimeout(2)
            client.connect(listener.getsockname())
            peer, _ = listener.accept()
            with peer:
                peer.settimeout(2)
                client.sendall(b"loopback")
                assert peer.recv(8) == b"loopback"


@pytest.mark.parametrize(
    "address",
    [
        ("203.0.113.1", 443),
        ("2001:db8::1", 443, 0, 0),
        ("192.168.1.1", 80),
        ("10.0.0.1", 80),
        ("172.16.0.1", 80),
        ("0.0.0.0", 80),
        ("::", 80, 0, 0),
        ("localhost", 80),
        ("example.com", 443),
        ("invalid-ip", 80),
        (2130706433, 80),
        (b"127.0.0.1", 80),
        ("::ffff:127.0.0.1", 80),
        ("::1%1", 80, 0, 1),
        (),
        ("127.0.0.1",),
        ("127.0.0.1", 80, 0),
        ["127.0.0.1", 80],
        "unknown-address-format",
        None,
    ],
)
def test_guard_rejects_before_underlying_connect(address, monkeypatch):
    attempts = []

    def record_connect(sock, destination):
        attempts.append(destination)

    monkeypatch.setattr(socket.socket, "connect", record_connect)
    block_live_network.__wrapped__(monkeypatch)
    with socket.socket() as client:
        with pytest.raises(AssertionError, match="Live network access is forbidden"):
            client.connect(address)
    assert attempts == []


def test_create_connection_remains_forbidden(monkeypatch):
    def unexpected_resolution(*args, **kwargs):
        pytest.fail("create_connection must be rejected before address resolution")

    monkeypatch.setattr(socket, "getaddrinfo", unexpected_resolution)
    with pytest.raises(AssertionError, match="Live network access is forbidden"):
        socket.create_connection(("127.0.0.1", 80))


@pytest.mark.parametrize("host", ["127.0.0.2", "127.1.2.3", "127.255.255.254"])
def test_guard_allows_ipv4_loopback_range(host, monkeypatch):
    attempts = []

    def record_connect(sock, destination):
        attempts.append(destination)

    monkeypatch.setattr(socket.socket, "connect", record_connect)
    block_live_network.__wrapped__(monkeypatch)
    with socket.socket() as client:
        client.connect((host, 80))
    assert attempts == [(host, 80)]
