"""WebSocket tối giản cho CDP, chỉ dùng thư viện chuẩn.

Vì sao tự viết: `agent_browser.py` cần nói chuyện với Chrome đang mở của người dùng
(để dùng phiên đã đăng nhập CVAT), mà việc đó bắt buộc phải qua WebSocket. Gói
`websocket-client` không cài được vì PyPI bị chặn từ máy này, còn venv lõi cũng
không có. CDP chỉ cần một tập con rất nhỏ của RFC 6455 nên tự viết rẻ hơn là thêm
một phụ thuộc không cài được.

Chỉ hỗ trợ đúng những gì CDP dùng: text frame, mặt nạ phía client, frame dài.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import struct
from urllib.parse import urlparse

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OP_TEXT = 0x1
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA


class WebSocketError(RuntimeError):
    pass


class SimpleWebSocket:
    """Client WebSocket đồng bộ, đủ để gọi CDP."""

    def __init__(self, url: str, *, timeout: float = 30.0) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "ws":
            raise WebSocketError(f"chỉ hỗ trợ ws://, nhận {parsed.scheme!r}")
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 80
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query

        self._socket = socket.create_connection((host, port), timeout=timeout)
        self._socket.settimeout(timeout)
        self._buffer = b""
        self._handshake(host, port, path)

    # -- bắt tay ---------------------------------------------------------- #
    def _handshake(self, host: str, port: int, path: str) -> None:
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        self._socket.sendall(request.encode())

        raw = b""
        while b"\r\n\r\n" not in raw:
            chunk = self._socket.recv(4096)
            if not chunk:
                raise WebSocketError("server đóng kết nối trong lúc bắt tay")
            raw += chunk
        head, _, rest = raw.partition(b"\r\n\r\n")
        status = head.split(b"\r\n", 1)[0].decode("latin-1")
        if "101" not in status:
            raise WebSocketError(f"bắt tay thất bại: {status}")
        expected = base64.b64encode(
            __import__("hashlib").sha1((key + GUID).encode()).digest()
        ).decode()
        if expected.lower() not in head.decode("latin-1").lower():
            raise WebSocketError("Sec-WebSocket-Accept không khớp")
        self._buffer = rest

    # -- gửi / nhận ------------------------------------------------------- #
    def send_text(self, text: str) -> None:
        payload = text.encode("utf-8")
        header = bytearray()
        header.append(0x80 | OP_TEXT)
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < (1 << 16):
            header.append(0x80 | 126)
            header += struct.pack(">H", length)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", length)
        mask = os.urandom(4)
        header += mask
        masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        self._socket.sendall(bytes(header) + masked)

    def _read_exact(self, count: int) -> bytes:
        while len(self._buffer) < count:
            chunk = self._socket.recv(65536)
            if not chunk:
                raise WebSocketError("kết nối đóng")
            self._buffer += chunk
        data, self._buffer = self._buffer[:count], self._buffer[count:]
        return data

    def recv_text(self) -> str:
        while True:
            first, second = self._read_exact(2)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._read_exact(8))[0]
            mask = self._read_exact(4) if masked else b""
            payload = self._read_exact(length)
            if masked:
                payload = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))

            if opcode == OP_TEXT:
                return payload.decode("utf-8", "replace")
            if opcode == OP_CLOSE:
                raise WebSocketError("server đóng kết nối")
            if opcode == OP_PING:
                self._send_control(OP_PONG, payload)
                continue
            # frame nhị phân / pong: bỏ qua

    def _send_control(self, opcode: int, payload: bytes) -> None:
        header = bytearray([0x80 | opcode])
        header.append(0x80 | len(payload))
        mask = os.urandom(4)
        header += mask
        masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        self._socket.sendall(bytes(header) + masked)

    def close(self) -> None:
        try:
            self._send_control(OP_CLOSE, b"")
        except Exception:  # pragma: no cover
            pass
        try:
            self._socket.close()
        except Exception:  # pragma: no cover
            pass


class CdpConnection:
    """Gọi CDP trên một WebSocket, khớp request/response theo `id`."""

    def __init__(self, url: str, *, timeout: float = 30.0) -> None:
        self._ws = SimpleWebSocket(url, timeout=timeout)
        self._next_id = 0

    def call(self, method: str, **params) -> dict:
        self._next_id += 1
        message_id = self._next_id
        self._ws.send_text(json.dumps({"id": message_id, "method": method, "params": params}))
        while True:
            data = json.loads(self._ws.recv_text())
            if data.get("id") == message_id:
                if "error" in data:
                    raise WebSocketError(f"{method}: {data['error']}")
                return data.get("result", {})

    def close(self) -> None:
        self._ws.close()
