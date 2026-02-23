"""Utility functions for UDP bridge."""

import ipaddress
import subprocess


def detect_wsl_ip() -> str:
    """Detect WSL IP address using wsl hostname command.

    :return: WSL IP address as string
    :raises SystemExit: If WSL detection fails or times out
    """
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


def validate_ip(ip: str) -> bool:
    """Validate an IP address string.

    :param ip: IP address to validate
    :return: True if valid
    :raises ValueError: If IP is invalid
    """
    ipaddress.ip_address(ip)
    return True

