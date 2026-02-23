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

import asyncio


async def main() -> None:
    """Main entry point for the UDP bridge service.

    :return: None
    """
    # Import here to avoid circular import warning when using python -m src
    from .cli import parse_args, create_config_from_args
    from .service import UDPBridgeService
    from .logging_utils import setup_logging, log

    args = parse_args()

    # Setup logging
    setup_logging(args.log_level)

    # Create and validate config
    config = create_config_from_args(args)

    service = UDPBridgeService(
        wsl_host=config.wsl_host,
        listen_port=config.listen_port,
        wsl_port=config.wsl_port,
        idle_timeout=config.idle_timeout,
        max_sessions=config.max_sessions,
        retry_attempts=config.retry_attempts,
        retry_delay=config.retry_delay,
    )

    log(f"Starting UDP bridge: {config.listen_port} -> {config.wsl_host}:{config.wsl_port}")
    try:
        await service.start()
    except OSError as exc:
        if exc.winerror == 10048:
            log(f"Port {config.listen_port} is already in use. Check if another instance is running.", "ERROR")
        else:
            log(f"OS error: {exc}", "ERROR")
        service.shutdown()
    except (KeyboardInterrupt, asyncio.CancelledError):
        log("Keyboard interrupt received")
        service.shutdown()
    except Exception as exc:
        log(f"Unexpected error: {exc}", "ERROR")
        service.shutdown()
        raise


def run() -> None:
    """Entry point for console script."""
    asyncio.run(main())


if __name__ == "__main__":
    run()

