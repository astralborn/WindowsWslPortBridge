# mypy: ignore-errors
"""
UDP Windows-to-WSL Port Bridge
============================

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
import subprocess
import sys
import time
import logging
import ipaddress
from dataclasses import dataclass, field
from typing import Dict, Tuple, Optional

ClientAddr = Tuple[str, int]


__version__ = "1.0.0"
__author__ = "Stanislav Nikolaievskyi"
__license__ = "MIT"


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='[%(asctime)s] %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def log(message: str, level: str = "INFO") -> None:
    getattr(logging, level.lower())(message)


def detect_wsl_ip() -> str:
    try:
        result = subprocess.run(
            ["wsl", "hostname", "-I"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        ip = result.stdout.strip().split()[0]
        if not ip:
            raise RuntimeError("No IP returned from WSL")
        
        # Validate IP address
        ipaddress.ip_address(ip)
        return ip
    except subprocess.TimeoutExpired:
        raise SystemExit("WSL hostname command timed out")
    except Exception as exc:
        raise SystemExit(f"Failed to detect WSL IP: {exc}")


@dataclass
class ClientSession:
    transport: asyncio.DatagramTransport
    protocol: "WSLProtocol"
    last_active: float
    created_at: float = field(default_factory=time.time)
    packets_forwarded: int = 0
    packets_received: int = 0


class UDPBridgeProtocol(asyncio.DatagramProtocol):
    def __init__(self, service: "UDPBridgeService") -> None:
        self.service = service
        self.transport: Optional[asyncio.DatagramTransport] = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self.transport = transport
        log(
            f"Listening on {transport.get_extra_info('sockname')} "
            f"-> WSL {self.service.wsl_host}:{self.service.wsl_port}"
        )

    def datagram_received(self, data: bytes, addr: ClientAddr) -> None:
        asyncio.create_task(self.service.forward_to_wsl(data, addr))

    def error_received(self, exc: Exception) -> None:
        log(f"Bridge socket error: {exc}", "ERROR")


class WSLProtocol(asyncio.DatagramProtocol):
    def __init__(self, client_addr: ClientAddr, bridge_transport: asyncio.DatagramTransport, service: "UDPBridgeService") -> None:
        self.client_addr = client_addr
        self.bridge_transport = bridge_transport
        self.service = service
        self.last_active = time.time()

    def refresh(self) -> None:
        self.last_active = time.time()

    def datagram_received(self, data: bytes, addr: ClientAddr) -> None:
        self.refresh()
        self.bridge_transport.sendto(data, self.client_addr)
        # Update session statistics
        for session in self.service.sessions.values():
            if session.protocol == self:
                session.packets_received += 1
                self.service.total_packets_received += 1
                break
        log(f"WSL -> {self.client_addr} ({len(data)} bytes)", "DEBUG")

    def error_received(self, exc: Exception) -> None:
        log(f"WSL session error {self.client_addr}: {exc}", "ERROR")


class UDPBridgeService:
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
        self.total_sessions_created = 0
        self.total_packets_forwarded = 0
        self.total_packets_received = 0

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        self.bridge_transport, _ = await loop.create_datagram_endpoint(
            lambda: UDPBridgeProtocol(self),
            local_addr=("0.0.0.0", self.listen_port),
        )

        asyncio.create_task(self._cleanup_loop())
        await self.shutdown_event.wait()

    async def forward_to_wsl(self, data: bytes, client: ClientAddr) -> None:
        if len(self.sessions) >= self.max_sessions and client not in self.sessions:
            log(f"Session limit reached, rejecting {client}", "WARNING")
            return
            
        if client not in self.sessions:
            # Create new session with retry logic
            for attempt in range(self.retry_attempts):
                try:
                    transport, protocol = await asyncio.get_running_loop().create_datagram_endpoint(
                        lambda: WSLProtocol(client, self.bridge_transport, self),
                        remote_addr=(self.wsl_host, self.wsl_port),
                    )
                    break
                except Exception as exc:
                    if attempt == self.retry_attempts - 1:
                        log(f"Failed to create session for {client} after {self.retry_attempts} attempts: {exc}", "ERROR")
                        return
                    log(f"Session creation attempt {attempt + 1} failed for {client}: {exc}, retrying...", "WARNING")
                    await asyncio.sleep(self.retry_delay)
            
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
        log("Shutting down bridge")
        self.shutdown_event.set()
        log(f"Final stats: {self.total_sessions_created} sessions created, "
            f"{self.total_packets_forwarded} packets sent, {self.total_packets_received} packets received")
        
        # Close all sessions
        for addr in list(self.sessions.keys()):
            asyncio.create_task(self._cleanup_session(addr))
        
        if self.bridge_transport:
            self.bridge_transport.close()


async def main() -> None:
    parser = argparse.ArgumentParser(description="UDP Windows-to-WSL Bridge")
    parser.add_argument("--wsl-host", help="WSL IP address")
    parser.add_argument("--listen-port", type=int, default=5060)
    parser.add_argument("--wsl-port", type=int, default=5060)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--max-sessions", type=int, default=1000, help="Maximum concurrent sessions")
    parser.add_argument("--retry-attempts", type=int, default=3, help="Connection retry attempts")
    parser.add_argument("--retry-delay", type=float, default=1.0, help="Delay between retries (seconds)")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO")

    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.log_level)
    
    # Validate configuration
    try:
        wsl_host = args.wsl_host or detect_wsl_ip()
        ipaddress.ip_address(wsl_host)
        
        if not (1 <= args.listen_port <= 65535):
            raise ValueError("Listen port must be 1-65535")
        if not (1 <= args.wsl_port <= 65535):
            raise ValueError("WSL port must be 1-65535")
        if args.timeout <= 0:
            raise ValueError("Timeout must be positive")
        if args.max_sessions <= 0:
            raise ValueError("Max sessions must be positive")
            
    except Exception as exc:
        log(f"Configuration validation failed: {exc}", "ERROR")
        sys.exit(1)

    service = UDPBridgeService(
        wsl_host=wsl_host,
        listen_port=args.listen_port,
        wsl_port=args.wsl_port,
        idle_timeout=args.timeout,
        max_sessions=args.max_sessions,
        retry_attempts=args.retry_attempts,
        retry_delay=args.retry_delay,
    )

    loop = asyncio.get_running_loop()
    # Windows doesn't support signal handlers in asyncio
    # Graceful shutdown will be handled by KeyboardInterrupt exception

    log(f"Starting UDP bridge: {args.listen_port} -> {wsl_host}:{args.wsl_port}")
    try:
        await service.start()
    except (KeyboardInterrupt, asyncio.CancelledError):
        log("Keyboard interrupt received")
        service.shutdown()
    except Exception as exc:
        log(f"Unexpected error: {exc}", "ERROR")
        service.shutdown()
        raise


if __name__ == "__main__":
    asyncio.run(main())
