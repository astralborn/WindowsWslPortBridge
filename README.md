 UDP Windows-to-WSL Port Bridge

A UDP port bridge that enables communication between a Windows host and a
Windows Subsystem for Linux (WSL) instance.

The bridge listens for UDP packets on a specified port on Windows,
forwards them to a UDP service running inside WSL, and relays responses
back to the original client. Per-client mappings are maintained to
support concurrent UDP flows, and idle connections are automatically
cleaned up.

---

## Background

Windows provides a built-in port proxy (`netsh interface portproxy`) for
TCP traffic, but **UDP is not supported**.

This project implements a UDP alternative using Python and `asyncio`,
allowing Windows applications to communicate with UDP services running
inside WSL.

---

## How It Works

The UDP Windows-to-WSL Bridge acts as an intermediary between UDP clients
on Windows and a UDP service running inside WSL.


1. The bridge listens on a specified UDP port on the Windows host.
2. When a UDP packet is received, the client’s source IP and port are
   used to identify the session.
3. If no existing session is found, a new UDP connection to the WSL
   host is created for that client.
4. Incoming packets are forwarded to the configured UDP port inside WSL.
5. Responses from the WSL service are relayed back to the original client.
6. Each client session tracks its last activity timestamp.
7. Idle sessions are automatically closed after a configurable timeout.

This design allows multiple clients to communicate concurrently with
UDP services running inside WSL while maintaining isolation between
client sessions.
