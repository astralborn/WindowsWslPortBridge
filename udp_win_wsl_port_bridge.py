# mypy: ignore-errors
"""
UDP Windows-to-WSL Port Bridge

This service enables UDP communication between a Windows host and a
Windows Subsystem for Linux (WSL) instance.

The bridge listens for UDP packets on a specified port on Windows,
forwards them to a UDP service running inside WSL, and relays responses
back to the originating client. Per-client mappings are maintained to
support concurrent UDP flows, and idle connections are automatically
cleaned up.

The service supports graceful shutdown via Ctrl+C and is intended to run
as a long-lived background process on Windows.

Notes:
- Windows does not provide a built-in UDP port proxy equivalent to
  `netsh interface portproxy` (TCP-only).
- This bridge fills that gap using an asyncio-based implementation.

Typical use cases:
- SIP / RTP development and testing
- Local UDP services inside WSL
- Game servers and custom UDP protocols

The WSL IP address can be specified manually or auto-detected using
`wsl hostname -I`.
"""


import argparse
import asyncio
import signal
import subprocess
import time
from dataclasses import dataclass
from typing import Dict, Tuple, Optional

ClientAddr = Tuple[str, int]


def log(message: str) -> None:
    """Simple timestamped logging."""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}")


def detect_wsl_ip() -> str:
    """Detect the first IP address of the running WSL instance."""
    try:
        result = subprocess.run(
            ["wsl", "hostname", "-I"],
            capture_output=True,
            text=True,
            check=True,
        )
        ip = result.stdout.strip().split()[0]
        if not ip:
            raise RuntimeError("No IP returned from WSL")
        return ip
    except Exception as exc:
        raise SystemExit(f"Failed to detect WSL IP: {exc}")


@dataclass
class ClientSession:
    transport: asyncio.DatagramTransport
    protocol: "WSLProtocol"
    last_active: float


class UDPBridgeProtocol(asyncio.DatagramProtocol):
    def __init__(self, service: "UDPBridgeService") -> None:
        self.service = service
        self.transport: Optional[asyncio.DatagramTransport] = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self.transport = transport
        log(f"Listening on {transport.get_extra_info('sockname')} "
            f"-> WSL {self.service.wsl_host}:{self.service.wsl_port}")

    def datagram_received(self, data: bytes, addr: ClientAddr) -> None:
        asyncio.create_task(self.service.forward_to_wsl(data, addr))

    def error_received(self, exc: Exception) -> None:
        log(f"Bridge socket error: {exc}")


class WSLProtocol(asyncio.DatagramProtocol):
    def __init__(self, client_addr: ClientAddr, bridge_transport: asyncio.DatagramTransport) -> None:
        self.client_addr = client_addr
        self.bridge_transport = bridge_transport
        self.last_active = time.time()

    def refresh(self) -> None:
        self.last_active = time.time()

    def datagram_received(self, data: bytes, addr: ClientAddr) -> None:
        self.refresh()
        self.bridge_transport.sendto(data, self.client_addr)
        log(f"WSL -> {self.client_addr} ({len(data)} bytes)")

    def error_received(self, exc: Exception) -> None:
        log(f"WSL session error {self.client_addr}: {exc}")


class UDPBridgeService:
    """Main service handling UDP forwarding and session management."""
    def __init__(self, wsl_host: str, listen_port: int, wsl_port: int, idle_timeout: float) -> None:
        self.wsl_host = wsl_host
        self.listen_port = listen_port
        self.wsl_port = wsl_port
        self.idle_timeout = idle_timeout
        self.sessions: Dict[ClientAddr, ClientSession] = {}
        self.shutdown_event = asyncio.Event()
        self.bridge_transport: Optional[asyncio.DatagramTransport] = None

    async def start(self) -> None:
        """Start the bridge service and wait until shutdown."""
        loop = asyncio.get_running_loop()
        self.bridge_transport, _ = await loop.create_datagram_endpoint(
            lambda: UDPBridgeProtocol(self),
            local_addr=("0.0.0.0", self.listen_port),
        )

        asyncio.create_task(self._cleanup_loop())
        await self.shutdown_event.wait()

    async def forward_to_wsl(self, data: bytes, client: ClientAddr) -> None:
        """Forward received client data to WSL and create session if needed."""
        if client not in self.sessions:
            transport, protocol = await asyncio.get_running_loop().create_datagram_endpoint(
                lambda: WSLProtocol(client, self.bridge_transport),
                remote_addr=(self.wsl_host, self.wsl_port),
            )
            self.sessions[client] = ClientSession(
                transport=transport,
                protocol=protocol,
                last_active=time.time(),
            )
            log(f"Session created: {client}")

        session = self.sessions[client]
        session.last_active = time.time()
        session.protocol.refresh()
        session.transport.sendto(data)
        log(f"{client} -> WSL ({len(data)} bytes)")

    async def _cleanup_loop(self) -> None:
        """Periodically remove idle sessions."""
        while not self.shutdown_event.is_set():
            now = time.time()
            stale = [addr for addr, s in self.sessions.items() if now - s.last_active > self.idle_timeout]

            for addr in stale:
                log(f"Closing idle session: {addr}")
                self.sessions.pop(addr).transport.close()

            await asyncio.sleep(1)

    async def shutdown(self) -> None:
        """Shutdown the bridge service and close all sessions."""
        if self.shutdown_event.is_set():
            return

        log("Shutting down bridge")
        self.shutdown_event.set()

        for session in self.sessions.values():
            session.transport.close()

        if self.bridge_transport:
            self.bridge_transport.close()


async def main() -> None:
    parser = argparse.ArgumentParser(description="UDP Windows-to-WSL Bridge")
    parser.add_argument("--wsl-host", help="WSL IP address")
    parser.add_argument("--listen-port", type=int, default=5060)
    parser.add_argument("--wsl-port", type=int, default=5060)
    parser.add_argument("--timeout", type=float, default=5.0)

    args = parser.parse_args()
    wsl_host = args.wsl_host or detect_wsl_ip()

    service = UDPBridgeService(
        wsl_host=wsl_host,
        listen_port=args.listen_port,
        wsl_port=args.wsl_port,
        idle_timeout=args.timeout,
    )

    # Ctrl+C handling
    signal.signal(signal.SIGINT, lambda *_: asyncio.create_task(service.shutdown()))

    await service.start()


if __name__ == "__main__":
    asyncio.run(main())
