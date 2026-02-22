# 🚀 UDP Windows-to-WSL Port Bridge

> A production-ready async UDP bridge enabling seamless communication between Windows
> and WSL with enterprise-grade features.

![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)
![Asyncio](https://img.shields.io/badge/Async-asyncio-green.svg)
![Platform](https://img.shields.io/badge/Platform-Windows%20%2B%20WSL-lightgrey.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)
![Version](https://img.shields.io/badge/Version-1.0.0-brightgreen.svg)

------------------------------------------------------------------------

## 📌 Overview

Windows provides a built-in TCP port proxy:

``` bash
netsh interface portproxy
```

However, **UDP is not supported**.

This project implements a **UDP port bridge** using Python and
`asyncio`, allowing Windows applications to communicate with UDP
services running inside WSL.

------------------------------------------------------------------------

## 📋 Table of Contents

- [📌 Overview](#-overview)
- [✨ Features](#-features)
- [🏗 Architecture](#-architecture)
- [🔎 How It Works](#-how-it-works)
- [⚙️ Installation](#️-installation)
- [▶️ Usage](#️-usage)
- [📊 Monitoring & Logging](#-monitoring--logging)
- [🧠 Design Decisions](#-design-decisions)
- [🛠 Use Cases](#-use-cases)
- [🐛 Troubleshooting](#-troubleshooting)
- [📄 License](#-license)
- [⭐ Contributing](#-contributing)

------------------------------------------------------------------------

## ✨ Features

-   🔄 UDP forwarding (Windows → WSL)
-   ⚡ Fully asynchronous (`asyncio`)
-   👥 Per-client session isolation
-   🧹 Automatic idle session cleanup
-   📦 Zero external dependencies
-   🧵 Supports concurrent UDP clients
-   🪶 Lightweight & efficient
-   🛡️ DoS protection (session limits)
-   🔁 Connection retry logic
-   📊 Session statistics & monitoring
-   📝 Structured logging with levels
-   ✅ Configuration validation
-   🪟 Windows-optimized (Ctrl+C shutdown)

------------------------------------------------------------------------

## 🏗 Architecture

    Windows UDP Client
            │
            ▼
    ┌────────────────────────┐
    │ UDP Bridge (Windows)   │
    │  - Session mapping     │
    │  - Activity tracking   │
    │  - Async forwarding    │
    └────────────────────────┘
            │
            ▼
    WSL UDP Service

------------------------------------------------------------------------

## 🔎 How It Works

1.  The bridge listens on a UDP port on Windows.
2.  When a packet is received:
    -   The client's source IP + port identifies the session.
3.  If no session exists:
    -   A new UDP socket is created toward WSL.
4.  Packets are forwarded to the WSL service.
5.  Responses are relayed back to the original client.
6.  Idle sessions are automatically cleaned up after a configurable
    timeout.

------------------------------------------------------------------------

## ⚙️ Installation

### Quick Start
```bash
# Clone the repository
git clone https://github.com/stanislav-nikolaievskyi/udp-windows-wsl-bridge.git
cd udp-windows-wsl-bridge

# Run directly (no dependencies required)
python udp_win_wsl_port_bridge.py
```

### Requirements

- **Python 3.9+** (for asyncio datagram endpoints)
- **Windows 10/11** with WSL2 installed
- **WSL instance** running UDP services

### No External Dependencies
This bridge uses only Python standard library modules - no `pip install` required!

------------------------------------------------------------------------

## ▶️ Usage

### Basic Usage
```bash
python udp_win_wsl_port_bridge.py
```

### Custom WSL IP
```bash
python udp_win_wsl_port_bridge.py --wsl-host 172.25.224.1
```

### Advanced Configuration
```bash
python udp_win_wsl_port_bridge.py --listen-port 9000 --wsl-port 9000 --timeout 60 --max-sessions 2000
```

### Production Example
```bash
python udp_win_wsl_port_bridge.py \
  --listen-port 5060 \
  --wsl-port 5060 \
  --timeout 30 \
  --max-sessions 5000 \
  --log-level INFO
```

### Debug Mode
```bash
python udp_win_wsl_port_bridge.py --log-level DEBUG --listen-port 5060
```

### Parameters

| Argument        | Description                              | Default        |
|---------------|------------------------------------------|---------------|
| `--wsl-host`    | WSL IP address (auto-detected if omitted) | `auto`        |
| `--listen-port` | UDP port to listen on (Windows side)    | `5060`        |
| `--wsl-port`    | Target UDP port inside WSL              | `5060`        |
| `--timeout`     | Idle session timeout (seconds)           | `5.0`         |
| `--max-sessions`| Maximum concurrent sessions              | `1000`        |
| `--retry-attempts`| Connection retry attempts               | `3`           |
| `--retry-delay` | Delay between retries (seconds)          | `1.0`         |
| `--log-level`   | Logging level (DEBUG/INFO/WARNING/ERROR) | `INFO`        |

## 📊 Monitoring & Logging

### Log Levels
- **DEBUG**: Detailed packet flow and session management
- **INFO**: General operation and session creation/cleanup
- **WARNING**: Retry attempts and session limit reached
- **ERROR**: Connection failures and critical errors

### Real-time Statistics
The bridge provides real-time monitoring:
```
[2024-01-01 12:00:00] INFO: Session created: ('192.168.1.100', 12345) (total: 1)
[2024-01-01 12:00:01] DEBUG: Active sessions: 1/1000, Total packets: 5 sent, 5 received
[2024-01-01 12:00:30] INFO: Shutting down bridge
[2024-01-01 12:00:30] INFO: Final stats: 1 sessions created, 5 packets sent, 5 packets received
```

### Graceful Shutdown
Press **Ctrl+C** to gracefully shutdown:
- Closes all active sessions
- Reports final statistics
- Releases all network resources

------------------------------------------------------------------------

## 🧠 Design Decisions

### Why per-client session mapping?

UDP is connectionless, but many protocols behave in a request--response
pattern.\
Maintaining per-client sockets prevents:

-   Packet mixing between clients
-   Session state conflicts
-   Response routing errors

------------------------------------------------------------------------

### Why asyncio?

-   Non-blocking I/O
-   Efficient handling of multiple concurrent clients
-   Minimal resource overhead
-   Clean event-driven architecture

------------------------------------------------------------------------

## 🛠 Use Cases

-   🎮 Game server development inside WSL
-   📡 Custom UDP protocols
-   🌐 DNS testing
-   📊 Telemetry services
-   🔬 Network tool development

------------------------------------------------------------------------

## 🐛 Troubleshooting

### Common Issues

#### "WSL hostname command timed out"
```bash
# Fix: Manually specify WSL IP
python udp_win_wsl_port_bridge.py --wsl-host 172.25.224.1
```

#### "Session limit reached"
```bash
# Fix: Increase session limit or check for connection leaks
python udp_win_wsl_port_bridge.py --max-sessions 5000 --log-level DEBUG
```

#### "Failed to create session"
```bash
# Fix: Increase retry attempts or check WSL service
python udp_win_wsl_port_bridge.py --retry-attempts 5 --retry-delay 2.0
```

### Getting WSL IP
```bash
# In WSL terminal
hostname -I
# Or from Windows
wsl hostname -I
```

### Debug Mode
Enable debug logging for detailed troubleshooting:
```bash
python udp_win_wsl_port_bridge.py --log-level DEBUG
```

------------------------------------------------------------------------

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

**Author**: Stanislav Nikolaievskyi
**Version**: 1.0.0

------------------------------------------------------------------------

## ⭐ Contributing

Contributions, issues, and feature requests are welcome!

### Development Setup
```bash
# Clone and test
git clone https://github.com/stanislav-nikolaievskyi/udp-windows-wsl-bridge.git
cd udp-windows-wsl-bridge
python udp_win_wsl_port_bridge.py --log-level DEBUG
```

### Submitting Changes
1. Fork the repository
2. Create a feature branch
3. Test thoroughly
4. Submit a pull request

If you find this useful, consider giving it a ⭐ on GitHub!

------------------------------------------------------------------------

## 🔗 Related Projects

- [netsh interface portproxy](https://docs.microsoft.com/en-us/windows-server/administration/windows-commands/netsh-interface-portproxy) - TCP-only Windows port proxy
- [WSL2 networking](https://docs.microsoft.com/en-us/windows/wsl/networking) - Official WSL networking documentation
