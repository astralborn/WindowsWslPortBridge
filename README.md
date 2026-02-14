# 🚀 UDP Windows-to-WSL Port Bridge

> A lightweight async UDP bridge enabling communication between Windows
> and WSL.

![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)
![Asyncio](https://img.shields.io/badge/Async-asyncio-green.svg)
![Platform](https://img.shields.io/badge/Platform-Windows%20%2B%20WSL-lightgrey.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

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

## ✨ Features

-   🔄 UDP forwarding (Windows → WSL)
-   ⚡ Fully asynchronous (`asyncio`)
-   👥 Per-client session isolation
-   🧹 Automatic idle session cleanup
-   📦 Zero external dependencies
-   🧵 Supports concurrent UDP clients
-   🪶 Lightweight & efficient

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

``` bash
git clone https://github.com/your-username/udp-windows-wsl-bridge.git
cd udp-windows-wsl-bridge
```

Requires:

-   Python 3.9+
-   Windows with WSL installed

------------------------------------------------------------------------

## ▶️ Usage

``` bash
python udp_win_wsl_port_bridge.py   --listen-host 0.0.0.0     --listen-port 9000     --wsl-host 172.25.224.1     --wsl-port 9000     --timeout 60
```

### Parameters

  Parameter         Description
  ----------------- --------------------------------
  `--listen-host`   Windows host IP to bind
  `--listen-port`   UDP port to listen on
  `--wsl-host`      WSL internal IP
  `--wsl-port`      Target UDP port inside WSL
  `--timeout`       Idle session timeout (seconds)

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

## 📄 License

MIT License

------------------------------------------------------------------------

# ⭐ Contributing

Contributions, issues, and feature requests are welcome.

If you find this useful, consider giving it a ⭐ on GitHub.
