# mypy: ignore-errors
"""
UDP Windows-to-WSL Port Bridge

This script enables UDP communication between Windows and a WSL (Windows Subsystem for Linux) instance.
It listens for UDP packets on a specified port on Windows, forwards them to a WSL host, and relays responses back to the original client.
The bridge manages client-to-WSL mappings, cleans up idle connections, and supports graceful shutdown via Ctrl+C, Ctrl+Z, or exit/quit commands.

For TCP bridging, use the Windows `netsh interface portproxy` feature (UDP is not supported by portproxy).
Example:
    netsh interface portproxy add v4tov4 listenport=5060 listenaddress=0.0.0.0 connectport=5060 connectaddress=<WSL_IP>

Firewall rules:
    Ensure Windows Firewall allows inbound traffic for both UDP and TCP on the listening port.
    Example (run as Administrator):
        netsh advfirewall firewall add rule name="UDP Bridge 5060" dir=in action=allow protocol=UDP localport=5060
        netsh advfirewall firewall add rule name="TCP Bridge 5060" dir=in action=allow protocol=TCP localport=5060

Usage:
    - Optionally set --wsl-host to your WSL IP address.
    - If not set, the script will auto-detect the WSL IP using `wsl hostname -I`.
    - Run the script on Windows.
    - Send UDP packets to LOCAL_UDP_PORT; they will be forwarded to WSL_UDP_PORT on the WSL host.

Features:
    - Automatic mapping and cleanup of client connections.
    - Logging with timestamps.
    - Graceful shutdown handling.
"""

import argparse
import asyncio
import signal
import sys
import time
import subprocess
from typing import Any, Dict, Tuple, Optional

# ---- CONFIG ----
LOCAL_UDP_PORT: int = 5060
WSL_UDP_PORT: int = 5060
UDP_RESPONSE_TIMEOUT: float = 5.0
# ----------------

client_map: Dict[Tuple[str, int], Tuple[asyncio.DatagramTransport, "WSLHandler"]] = {}
shutdown_event: asyncio.Event = asyncio.Event()

def log(*args: Any) -> None:
    """
    Log messages with a timestamp.

    :param args: Arguments to print.
    :return: None
    """
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ", *args)

def detect_wsl_ip() -> str:
    """
    Detect the WSL host IP address using `wsl hostname -I`.

    :return: The detected WSL IP address as a string.
    :raises SystemExit: If detection fails.
    """
    try:
        result = subprocess.run(
            ["wsl", "hostname", "-I"],
            capture_output=True,
            text=True,
            check=True
        )
        ips = result.stdout.strip().split()
        if not ips or not ips[0]:
            log("Error: No IPs found from `wsl hostname -I`. Please specify --wsl-host manually.")
            sys.exit(1)
        return ips[0]
    except Exception as e:
        log(f"Error: Failed to detect WSL IP: {e}. Please specify --wsl-host manually.")
        sys.exit(1)


class UDPBridge(asyncio.DatagramProtocol):
    """
    Listens on Windows and forwards packets to WSL.
    """
    def __init__(self, wsl_host: str) -> None:
        """
        :param wsl_host: The IP address of the WSL host.
        :return: None
        """
        self.wsl_host: str = wsl_host
        self.transport: Optional[asyncio.DatagramTransport] = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        """
        Called when the UDP socket is created and ready.

        :param transport: The UDP transport.
        :return: None
        """
        self.transport = transport
        log(f"UDP bridge listening on {transport.get_extra_info('sockname')} -> WSL {self.wsl_host}:{WSL_UDP_PORT}")

    def datagram_received(self, data: bytes, addr: Tuple[str, int]) -> None:
        """
        Handle incoming UDP datagrams from clients.

        :param data: The UDP packet data.
        :param addr: The address of the client.
        :return: None
        """
        asyncio.create_task(self.forward_to_wsl(data, addr))

    async def forward_to_wsl(self, data: bytes, client_addr: Tuple[str, int]) -> None:
        """
        Forward a UDP packet to the WSL host, creating a new mapping if needed.

        :param data: The UDP packet data.
        :param client_addr: The address of the client.
        :return: None
        """
        if client_addr not in client_map:
            loop = asyncio.get_running_loop()
            transport, protocol = await loop.create_datagram_endpoint(
                lambda: WSLHandler(client_addr, self.transport),
                remote_addr=(self.wsl_host, WSL_UDP_PORT)
            )
            client_map[client_addr] = (transport, protocol)
            log(f"New mapping created for client {client_addr} -> WSL:{WSL_UDP_PORT}")

        transport, protocol = client_map[client_addr]
        protocol.refresh()
        transport.sendto(data)

    def error_received(self, exc: Exception) -> None:
        """
        Handle errors received on the UDP socket.

        :param exc: The exception received.
        :return: None
        """
        log("UDP bridge error:", exc)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        """
        Handle closure of the UDP socket.

        :param exc: The exception, if any.
        :return: None
        """
        log("UDP bridge connection lost:", exc)

class WSLHandler(asyncio.DatagramProtocol):
    """
    Forwards replies from WSL back to the client.
    """
    def __init__(self, client_addr: Tuple[str, int], main_transport: Optional[asyncio.DatagramTransport]) -> None:
        """
        :param client_addr: The address of the client.
        :param main_transport: The main UDP transport to send data back to the client.
        :return: None
        """
        self.client_addr: Tuple[str, int] = client_addr
        self.main_transport: Optional[asyncio.DatagramTransport] = main_transport
        self.last_active: float = time.time()

    def refresh(self) -> None:
        """
        Update the last active timestamp.

        :return: None
        """
        self.last_active = time.time()

    def datagram_received(self, data: bytes, addr: Tuple[str, int]) -> None:
        """
        Forward UDP replies from WSL to the client.

        :param data: The UDP packet data.
        :param addr: The address of the sender (WSL).
        :return: None
        """
        if self.main_transport:
            self.main_transport.sendto(data, self.client_addr)
        log(f"UDP: {len(data)} bytes WSL -> client {self.client_addr}")

    def error_received(self, exc: Exception) -> None:
        """
        Handle errors received on the WSL UDP socket.

        :param exc: The exception received.
        :return: None
        """
        log(f"WSLHandler error for {self.client_addr}:", exc)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        """
        Handle closure of the WSL UDP socket.

        :param exc: The exception, if any.
        :return: None
        """
        log(f"WSLHandler closed for {self.client_addr}")

async def cleanup_idle_connections() -> None:
    """
    Close idle WSL connections to free resources.

    :return: None
    """
    while not shutdown_event.is_set():
        now = time.time()
        stale = [c for c, (_, proto) in client_map.items() if now - proto.last_active > UDP_RESPONSE_TIMEOUT]
        for c in stale:
            log(f"Closing idle connection for {c}")
            transport, _ = client_map.pop(c)
            transport.close()
        await asyncio.sleep(1)

async def wait_for_exit() -> None:
    """
    Waits for Ctrl+Z (EOF) or Ctrl+C (SIGINT).
    """

    def handle_sigint(_sig: int, _frame: Any) -> None:
        log("SIGINT (Ctrl+C) received.")
        shutdown_event.set()

    signal.signal(signal.SIGINT, handle_sigint)
    log("Bridge running. Press Ctrl+C or Ctrl+Z+Enter to stop.")

    try:
        while not shutdown_event.is_set():
            line = await asyncio.to_thread(sys.stdin.readline)
            if not line:  # EOF (Ctrl+Z + Enter)
                log("EOF received (Ctrl+Z).")
                shutdown_event.set()
            elif line.strip().lower() in ("exit", "quit"):
                shutdown_event.set()
    except Exception as e:
        log("Input monitor stopped:", e)


async def main(wsl_host: str) -> None:
    """
    Main entry point: starts the UDP bridge and manages shutdown.

    :param wsl_host: The IP address of the WSL host.
    :return: None
    """
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: UDPBridge(wsl_host),
        local_addr=('0.0.0.0', LOCAL_UDP_PORT)
    )

    try:
        await asyncio.gather(wait_for_exit(), cleanup_idle_connections())
    finally:
        log("Stopping bridge...")
        shutdown_event.set()
        for transport, _ in list(client_map.values()):
            transport.close()
        transport.close()
        log("Bridge fully shut down.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UDP Windows-to-WSL Port Bridge")
    parser.add_argument(
        "--wsl-host",
        help="IP address of the WSL host (if not set, auto-detect using `wsl hostname -I`)"
    )
    args = parser.parse_args()
    wsl_host_ip = args.wsl_host or detect_wsl_ip()
    asyncio.run(main(wsl_host_ip))
