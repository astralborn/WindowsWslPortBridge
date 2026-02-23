"""UDP Bridge Service implementation."""

import asyncio
import time
from typing import Dict, Optional

from .models import ClientAddr, ClientSession
from .protocols import UDPBridgeProtocol, WSLProtocol
from .logging_utils import log


class UDPBridgeService:
    """Main UDP bridge service that forwards packets between Windows and WSL."""

    def __init__(
        self,
        wsl_host: str,
        listen_port: int,
        wsl_port: int,
        idle_timeout: float,
        max_sessions: int = 1000,
        retry_attempts: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        """Initialize UDP bridge service.

        :param wsl_host: WSL IP address
        :param listen_port: Port to listen on Windows
        :param wsl_port: Target port in WSL
        :param idle_timeout: Session idle timeout in seconds
        :param max_sessions: Maximum concurrent sessions
        :param retry_attempts: Connection retry attempts
        :param retry_delay: Delay between retries in seconds
        :return: None
        """
        self.wsl_host = wsl_host
        self.listen_port = listen_port
        self.wsl_port = wsl_port
        self.idle_timeout = idle_timeout
        self.max_sessions = max_sessions
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        self.sessions: Dict[ClientAddr, ClientSession] = {}
        self.shutdown_event = asyncio.Event()
        self.bridge_transport: Optional[asyncio.DatagramTransport] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self.total_sessions_created = 0
        self.total_packets_forwarded = 0
        self.total_packets_received = 0

    async def start(self) -> None:
        """Start the UDP bridge service.

        :return: None
        """
        loop = asyncio.get_running_loop()
        self.bridge_transport, _ = await loop.create_datagram_endpoint(
            lambda: UDPBridgeProtocol(self),
            local_addr=("0.0.0.0", self.listen_port),
        )

        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        await self.shutdown_event.wait()

    async def forward_to_wsl(self, data: bytes, client: ClientAddr) -> None:
        """Forward UDP packet from client to WSL.

        :param data: UDP packet data
        :param client: Client address tuple (IP, port)
        :return: None
        """
        if len(self.sessions) >= self.max_sessions and client not in self.sessions:
            log(f"Session limit reached, rejecting {client}", "WARNING")
            return

        if client not in self.sessions:
            # Create new session with retry logic
            transport: Optional[asyncio.DatagramTransport] = None
            protocol: Optional[WSLProtocol] = None
            for attempt in range(self.retry_attempts):
                try:
                    # Capture client in default argument to avoid closure bug
                    transport, protocol = await asyncio.get_running_loop().create_datagram_endpoint(
                        lambda c=client: WSLProtocol(c, self.bridge_transport, self),
                        remote_addr=(self.wsl_host, self.wsl_port),
                    )
                    break
                except Exception as exc:
                    if attempt == self.retry_attempts - 1:
                        log(f"Failed to create session for {client} after {self.retry_attempts} attempts: {exc}", "ERROR")
                        return
                    log(f"Session creation attempt {attempt + 1} failed for {client}: {exc}, retrying...", "WARNING")
                    await asyncio.sleep(self.retry_delay)

            # Safety check: ensure transport and protocol were created
            if transport is None or protocol is None:
                log(f"Failed to create session for {client}: transport or protocol is None", "ERROR")
                return

            self.sessions[client] = ClientSession(
                transport=transport,
                protocol=protocol,
                last_active=time.time(),
            )
            self.total_sessions_created += 1
            log(f"Session created: {client} (total: {self.total_sessions_created})")

        session = self.sessions[client]
        try:
            session.last_active = time.time()
            session.protocol.refresh()
            session.transport.sendto(data)
            session.packets_forwarded += 1
            self.total_packets_forwarded += 1
            log(f"{client} -> WSL ({len(data)} bytes)", "DEBUG")
        except Exception as exc:
            log(f"Failed to forward packet from {client}: {exc}", "ERROR")
            await self._cleanup_session(client)

    async def _cleanup_loop(self) -> None:
        """Background loop to cleanup idle sessions.

        :return: None
        """
        while not self.shutdown_event.is_set():
            now = time.time()
            stale = [
                addr for addr, s in self.sessions.items()
                if now - s.last_active > self.idle_timeout
            ]
            for addr in stale:
                await self._cleanup_session(addr)

            # Log session statistics periodically
            if len(self.sessions) > 0:
                log(f"Active sessions: {len(self.sessions)}/{self.max_sessions}, "
                    f"Total packets: {self.total_packets_forwarded} sent, {self.total_packets_received} received", "DEBUG")

            await asyncio.sleep(1)

    async def _cleanup_session(self, addr: ClientAddr) -> None:
        """Cleanup and close a specific session.

        :param addr: Client address to cleanup
        :return: None
        """
        if addr in self.sessions:
            log(f"Closing session: {addr}", "DEBUG")
            session = self.sessions.pop(addr)
            try:
                session.transport.close()
                # Give transport time to close properly
                await asyncio.sleep(0.1)
            except Exception as exc:
                log(f"Error closing session {addr}: {exc}", "WARNING")

    def shutdown(self) -> None:
        """Shutdown the bridge service gracefully.

        :return: None
        """
        log("Shutting down bridge")
        self.shutdown_event.set()

        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()

        log(f"Final stats: {self.total_sessions_created} sessions created, "
            f"{self.total_packets_forwarded} packets sent, {self.total_packets_received} packets received")

        # Close all sessions
        for addr in list(self.sessions.keys()):
            asyncio.create_task(self._cleanup_session(addr))

        if self.bridge_transport:
            self.bridge_transport.close()

