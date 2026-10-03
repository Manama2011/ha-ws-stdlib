#!/usr/bin/env python3
"""Minimal WebSocket client for the Home Assistant Core API - standard library only.

The SSH add-on ships neither `websockets` nor `websocket-client`, and pip is locked by
PEP 668. This script speaks the WebSocket protocol directly, so WebSocket-only commands
(config/entity_registry/update, label and category registry, lovelace/config/save,
repairs/list_issues ...) work without installing anything.

Usage: a JSON list of commands WITHOUT "id" on stdin, the results as a JSON list on
stdout. A single command object is accepted as well.

  echo '[{"type":"config/label_registry/list"}]' | python3 ha_ws.py

Environment:
  SUPERVISOR_TOKEN  set automatically inside add-ons (used by default)
  HA_WS_TOKEN       alternative token, e.g. a long-lived access token
  HA_WS_HOST        default "supervisor"     (direct: your HA host)
  HA_WS_PORT        default 80               (direct: 8123)
  HA_WS_PATH        default "/core/websocket" (direct: "/api/websocket")
  HA_WS_TIMEOUT     socket timeout in seconds, default 30

Plain ws:// only (no TLS). Subscriptions are not supported: for every command the
script waits for its "result" message and ignores events.
"""
import base64
import json
import os
import socket
import struct
import sys

HOST = os.environ.get("HA_WS_HOST", "supervisor")
PORT = int(os.environ.get("HA_WS_PORT", "80"))
PATH = os.environ.get("HA_WS_PATH", "/core/websocket")
TIMEOUT = float(os.environ.get("HA_WS_TIMEOUT", "30"))


class WS:
    def __init__(self, host, port, path):
        self.sock = socket.create_connection((host, port), timeout=TIMEOUT)
        self.buf = b""
        key = base64.b64encode(os.urandom(16)).decode()
        handshake = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(handshake.encode())
        while b"\r\n\r\n" not in self.buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("connection closed during handshake")
            self.buf += chunk
        head, self.buf = self.buf.split(b"\r\n\r\n", 1)
        if b"101" not in head.split(b"\r\n")[0]:
            raise RuntimeError("handshake failed: " + head.decode(errors="replace"))

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise RuntimeError("connection closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def _frame(self, opcode, payload):
        """Send one frame; client frames must be masked (RFC 6455)."""
        header = bytearray([0x80 | opcode])  # FIN + opcode
        mask = os.urandom(4)
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", n)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def send(self, obj):
        self._frame(0x1, json.dumps(obj).encode())

    def recv(self):
        """Return the next JSON message; answers pings, joins fragmented messages."""
        parts = []
        while True:
            b0, b1 = self._read(2)
            fin, opcode = b0 & 0x80, b0 & 0x0F
            length = b1 & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._read(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._read(8))[0]
            mask = self._read(4) if b1 & 0x80 else None  # servers normally do not mask
            data = self._read(length) if length else b""
            if mask:
                data = bytes(c ^ mask[i % 4] for i, c in enumerate(data))
            if opcode == 0x8:
                raise RuntimeError("server closed the connection")
            if opcode == 0x9:  # ping -> pong with the same payload
                self._frame(0xA, data)
                continue
            if opcode == 0xA:  # unsolicited pong
                continue
            if opcode in (0x0, 0x1, 0x2):
                parts.append(data)
                if fin:
                    return json.loads(b"".join(parts))

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def main():
    token = os.environ.get("HA_WS_TOKEN") or os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        sys.exit("no token: set SUPERVISOR_TOKEN (add-on) or HA_WS_TOKEN")
    commands = json.load(sys.stdin)
    if isinstance(commands, dict):
        commands = [commands]

    ws = WS(HOST, PORT, PATH)
    try:
        ws.recv()  # auth_required
        ws.send({"type": "auth", "access_token": token})
        auth = ws.recv()
        if auth.get("type") != "auth_ok":
            raise RuntimeError(f"authentication failed: {auth}")

        results = []
        for i, cmd in enumerate(commands, start=1):
            ws.send(dict(cmd, id=i))
            while True:
                res = ws.recv()
                if res.get("id") == i and res.get("type") == "result":
                    results.append(res)
                    break
        json.dump(results, sys.stdout, indent=2, ensure_ascii=False)
        print()
    finally:
        ws.close()


if __name__ == "__main__":
    main()
