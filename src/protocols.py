"""Protocol implementations for UDP bridge."""

import asyncio
import time
from typing import Optional, TYPE_CHECKING

from .models import ClientAddr
from .logging_utils import log

if TYPE_CHECKING:
    from .service import UDPBridgeService


class UDPBridgeProtocol(asyncio.DatagramProtocol):
    """Protocol for the main UDP bridge listener."""

    def __init__(self, service: "UDPBridgeService") -> None:
        """Initialize UDP bridge protocol.

        :param service: UDP bridge service instance
        :return: None
        """
        self.service = service
        self.transport: Optional[asyncio.DatagramTransport] = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        """Called when connection is established.

        :param transport: Datagram transport instance
        :return: None
        """
        self.transport = transport
        log(
            f"Listening on {transport.get_extra_info('sockname')} "
            f"-> WSL {self.service.wsl_host}:{self.service.wsl_port}"
        )

    def datagram_received(self, data: bytes, addr: ClientAddr) -> None:
        """Handle incoming UDP datagram.

        :param data: Received data
        :param addr: Source address
        :return: None
        """
        asyncio.create_task(self.service.forward_to_wsl(data, addr))

    def error_received(self, exc: Exception) -> None:
        """Handle socket error.

        :param exc: Exception that occurred
        :return: None
        """
        log(f"Bridge socket error: {exc}", "ERROR")


class WSLProtocol(asyncio.DatagramProtocol):
    """Protocol for individual client sessions to WSL."""

    def __init__(
        self,
        client_addr: ClientAddr,
        bridge_transport: asyncio.DatagramTransport,
        service: "UDPBridgeService"
    ) -> None:
        """Initialize WSL protocol for client session.

        :param client_addr: Client address tuple
        :param bridge_transport: Bridge transport for sending responses
        :param service: UDP bridge service instance
        :return: None
        """
        self.client_addr = client_addr
        self.bridge_transport = bridge_transport
        self.service = service
        self.last_active = time.time()
        self.transport: Optional[asyncio.DatagramTransport] = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        """Called when connection is established.

        :param transport: Datagram transport instance
        :return: None
        """
        self.transport = transport

    def connection_lost(self, exc: Optional[Exception]) -> None:
        """Called when connection is lost.

        :param exc: Exception that caused the loss, or None
        :return: None
        """
        if exc:
            log(f"Connection lost for {self.client_addr}: {exc}", "WARNING")

    def refresh(self) -> None:
        """Refresh the last active timestamp.

        :return: None
        """
        self.last_active = time.time()

    def datagram_received(self, data: bytes, addr: ClientAddr) -> None:
        """Handle response from WSL service.

        :param data: Response data from WSL
        :param addr: WSL service address
        :return: None
        """
        self.refresh()
        self.bridge_transport.sendto(data, self.client_addr)
        # Update session statistics - direct lookup
        session = self.service.sessions.get(self.client_addr)
        if session:
            session.packets_received += 1
            self.service.total_packets_received += 1
        log(f"WSL -> {self.client_addr} ({len(data)} bytes)", "DEBUG")

    def error_received(self, exc: Exception) -> None:
        """Handle WSL session error.

        :param exc: Exception that occurred
        :return: None
        """
        log(f"WSL session error {self.client_addr}: {exc}", "ERROR")

