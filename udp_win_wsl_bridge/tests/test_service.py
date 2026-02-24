"""Tests for UDPBridgeService."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ..service import UDPBridgeService
from ..models import ClientSession


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_service(**kwargs) -> UDPBridgeService:
    defaults = dict(
        wsl_host="127.0.0.1",
        listen_port=15060,
        wsl_port=15061,
        idle_timeout=5.0,
        max_sessions=10,
        retry_attempts=3,
        retry_delay=0.0,
    )
    defaults.update(kwargs)
    return UDPBridgeService(**defaults)


def make_mock_transport() -> MagicMock:
    t = MagicMock()
    t.sendto = MagicMock()
    t.close = MagicMock()
    return t


def make_mock_session(last_active: float | None = None) -> ClientSession:
    session = ClientSession(
        transport=make_mock_transport(),
        protocol=MagicMock(),
    )
    if last_active is not None:
        session.last_active = last_active
    return session


# ---------------------------------------------------------------------------
# track_task
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_track_task_removes_on_completion():
    svc = make_service()

    async def noop():
        pass

    task = asyncio.create_task(noop())
    svc.track_task(task)
    assert task in svc._pending_tasks
    await task
    # Callback fires synchronously when the task result is retrieved
    await asyncio.sleep(0)
    assert task not in svc._pending_tasks


# ---------------------------------------------------------------------------
# forward_to_wsl – session limit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_forward_rejects_when_session_limit_reached():
    svc = make_service(max_sessions=2)
    svc.bridge_transport = make_mock_transport()

    # Pre-fill sessions up to the limit
    svc.sessions[("1.1.1.1", 1001)] = make_mock_session()
    svc.sessions[("1.1.1.2", 1002)] = make_mock_session()

    new_client = ("1.1.1.3", 1003)
    await svc.forward_to_wsl(b"hello", new_client)

    assert new_client not in svc.sessions
    assert svc.total_packets_forwarded == 0


@pytest.mark.asyncio
async def test_forward_allows_existing_client_at_limit():
    """An existing client must still get through even when the session limit
    is fully saturated."""
    svc = make_service(max_sessions=1)
    svc.bridge_transport = make_mock_transport()

    existing = ("1.1.1.1", 1001)
    session = make_mock_session()
    svc.sessions[existing] = session

    await svc.forward_to_wsl(b"hello", existing)

    session.transport.sendto.assert_called_once_with(b"hello")
    assert svc.total_packets_forwarded == 1


# ---------------------------------------------------------------------------
# forward_to_wsl – session creation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_forward_creates_new_session():
    svc = make_service()
    svc.bridge_transport = make_mock_transport()

    mock_transport = make_mock_transport()
    mock_protocol = MagicMock()

    with patch.object(
        asyncio.get_event_loop().__class__,
        "create_datagram_endpoint",
        new_callable=AsyncMock,
        return_value=(mock_transport, mock_protocol),
    ):
        client = ("2.2.2.2", 2000)
        await svc.forward_to_wsl(b"data", client)

    assert client in svc.sessions
    assert svc.total_sessions_created == 1
    assert svc.total_packets_forwarded == 1


@pytest.mark.asyncio
async def test_forward_drops_when_bridge_transport_not_ready():
    svc = make_service()
    # bridge_transport is None (not started)

    client = ("3.3.3.3", 3000)
    await svc.forward_to_wsl(b"data", client)

    assert client not in svc.sessions
    assert svc.total_packets_forwarded == 0


# ---------------------------------------------------------------------------
# _create_session – retry logic
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_session_succeeds_after_retries():
    svc = make_service(retry_attempts=3, retry_delay=0.0)
    svc.bridge_transport = make_mock_transport()

    mock_transport = make_mock_transport()
    mock_protocol = MagicMock()
    call_count = 0

    async def flaky_endpoint(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise OSError("connection refused")
        return mock_transport, mock_protocol

    loop = asyncio.get_running_loop()
    with patch.object(loop, "create_datagram_endpoint", side_effect=flaky_endpoint):
        session = await svc._create_session(("4.4.4.4", 4000))

    assert session is not None
    assert call_count == 3


@pytest.mark.asyncio
async def test_create_session_returns_none_after_all_retries_fail():
    svc = make_service(retry_attempts=2, retry_delay=0.0)
    svc.bridge_transport = make_mock_transport()

    loop = asyncio.get_running_loop()
    with patch.object(
        loop,
        "create_datagram_endpoint",
        new_callable=AsyncMock,
        side_effect=OSError("always fails"),
    ):
        session = await svc._create_session(("5.5.5.5", 5000))

    assert session is None


# ---------------------------------------------------------------------------
# _cleanup_session
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cleanup_session_removes_and_closes():
    svc = make_service()
    addr = ("6.6.6.6", 6000)
    session = make_mock_session()
    svc.sessions[addr] = session

    await svc._cleanup_session(addr)

    assert addr not in svc.sessions
    session.transport.close.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_session_is_idempotent():
    """Cleaning up an already-removed session must not raise."""
    svc = make_service()
    await svc._cleanup_session(("7.7.7.7", 7000))  # Not in sessions – should be silent


# ---------------------------------------------------------------------------
# _cleanup_loop – idle detection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cleanup_loop_removes_stale_sessions():
    svc = make_service(idle_timeout=0.1)
    svc.bridge_transport = make_mock_transport()

    addr = ("8.8.8.8", 8000)
    stale_session = make_mock_session(last_active=time.time() - 1.0)
    svc.sessions[addr] = stale_session

    # Run the loop long enough for one tick
    task = asyncio.create_task(svc._cleanup_loop())
    await asyncio.sleep(0.25)
    svc.shutdown_event.set()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert addr not in svc.sessions
    stale_session.transport.close.assert_called_once()


# ---------------------------------------------------------------------------
# shutdown / async_shutdown
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_async_shutdown_closes_all_sessions():
    svc = make_service()
    svc.bridge_transport = make_mock_transport()

    for i in range(3):
        svc.sessions[(f"9.9.9.{i}", 9000 + i)] = make_mock_session()

    await svc.async_shutdown()

    assert not svc.sessions
    svc.bridge_transport.close.assert_called_once()


@pytest.mark.asyncio
async def test_async_shutdown_awaits_pending_tasks():
    svc = make_service()
    svc.bridge_transport = make_mock_transport()
    completed = []

    async def slow_task():
        await asyncio.sleep(0.05)
        completed.append(True)

    task = asyncio.create_task(slow_task())
    svc.track_task(task)

    await svc.async_shutdown()

    assert completed == [True]


# ---------------------------------------------------------------------------
# ClientSession.refresh
# ---------------------------------------------------------------------------

def test_session_refresh_updates_last_active():
    session = make_mock_session()
    before = session.last_active
    time.sleep(0.01)
    session.refresh()
    assert session.last_active > before
