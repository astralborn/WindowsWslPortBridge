"""Data models for UDP bridge."""

import time
from dataclasses import dataclass, field
from typing import Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    import asyncio
    from .protocols import WSLProtocol

ClientAddr = Tuple[str, int]


@dataclass
class ClientSession:
    """Represents a client session with WSL."""

    transport: "asyncio.DatagramTransport"
    protocol: "WSLProtocol"
    last_active: float
    created_at: float = field(default_factory=time.time)
    packets_forwarded: int = 0
    packets_received: int = 0

