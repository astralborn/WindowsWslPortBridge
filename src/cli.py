"""Command-line interface for UDP bridge."""

import argparse
import ipaddress
import sys

from .config import BridgeConfig
from .utils import detect_wsl_ip
from .logging_utils import log


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    :return: Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="UDP Windows-to-WSL Bridge",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--wsl-host",
        help="WSL IP address (auto-detected if not specified)"
    )
    parser.add_argument(
        "--listen-port",
        type=int,
        default=5060,
        help="Port to listen on Windows"
    )
    parser.add_argument(
        "--wsl-port",
        type=int,
        default=5060,
        help="Target port in WSL"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Session idle timeout in seconds"
    )
    parser.add_argument(
        "--max-sessions",
        type=int,
        default=1000,
        help="Maximum concurrent sessions"
    )
    parser.add_argument(
        "--retry-attempts",
        type=int,
        default=3,
        help="Connection retry attempts"
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=1.0,
        help="Delay between retries (seconds)"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level"
    )

    return parser.parse_args()


def create_config_from_args(args: argparse.Namespace) -> BridgeConfig:
    """Create BridgeConfig from parsed arguments.

    :param args: Parsed arguments
    :return: BridgeConfig instance
    :raises SystemExit: If configuration is invalid
    """
    try:
        wsl_host = args.wsl_host or detect_wsl_ip()
        ipaddress.ip_address(wsl_host)

        config = BridgeConfig(
            wsl_host=wsl_host,
            listen_port=args.listen_port,
            wsl_port=args.wsl_port,
            idle_timeout=args.timeout,
            max_sessions=args.max_sessions,
            retry_attempts=args.retry_attempts,
            retry_delay=args.retry_delay,
            log_level=args.log_level,
        )
        config.validate()
        return config

    except Exception as exc:
        log(f"Configuration validation failed: {exc}", "ERROR")
        sys.exit(1)

