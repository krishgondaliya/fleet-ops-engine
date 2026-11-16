"""The autouse network guard (conftest.py) must still block outbound connections after allowing loopback."""
import socket

import pytest


def test_outbound_connections_are_blocked():
    with pytest.raises(RuntimeError, match="offline test"):
        socket.create_connection(("api.anthropic.com", 443), timeout=1)
    s = socket.socket()
    try:
        with pytest.raises(RuntimeError, match="offline test"):
            s.connect(("93.184.216.34", 80))
    finally:
        s.close()
