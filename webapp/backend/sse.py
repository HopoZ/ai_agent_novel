"""Server-Sent Events 封装（run_stream）。"""

import json
from typing import Any


def sse_pack(event: str, data: Any) -> bytes:
    payload = json.dumps({"event": event, "data": data}, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")
