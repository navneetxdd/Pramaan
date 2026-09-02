from __future__ import annotations



import socket



import pytest



from engine.app.core.logging_setup import block_outbound_sockets, restore_outbound_sockets





@pytest.fixture(autouse=True)

def _reset_socket_guard(monkeypatch: pytest.MonkeyPatch) -> None:

    restore_outbound_sockets()

    monkeypatch.delenv("PRAMAAN_ALLOW_LOGICAL_ACQUIRE", raising=False)

    yield

    restore_outbound_sockets()





def test_outbound_socket_guard_blocks_remote() -> None:

    block_outbound_sockets()

    with pytest.raises(OSError, match="Outbound network blocked"):

        socket.create_connection(("8.8.8.8", 53), timeout=1)





def test_outbound_socket_guard_allows_localhost() -> None:

    block_outbound_sockets()

    try:

        socket.create_connection(("127.0.0.1", 65533), timeout=0.2)

    except OSError as exc:

        assert "Outbound network blocked" not in str(exc)

