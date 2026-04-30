from __future__ import annotations

import json
import os
import sys
import threading
import time
from typing import Any, Dict

from fastapi.testclient import TestClient

from webapp.backend.server import app


def _write_frame(pipe, payload: Dict[str, Any], lock: threading.Lock) -> None:
    raw = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
    with lock:
        pipe.write(raw)
        pipe.flush()


def _iter_sse_frames(lines_iter):
    event_name = "message"
    data_parts = []
    for line in lines_iter:
        if line is None:
            continue
        if isinstance(line, (bytes, bytearray)):
            ln = line.decode("utf-8", errors="replace").rstrip("\r")
        else:
            ln = str(line).rstrip("\r")
        if not ln:
            if data_parts:
                raw_data = "".join(data_parts)
                try:
                    parsed = json.loads(raw_data)
                    data = parsed.get("data") if isinstance(parsed, dict) else parsed
                except Exception:
                    data = {"raw": raw_data}
                yield event_name, data
            event_name = "message"
            data_parts = []
            continue
        if ln.startswith("event:"):
            event_name = ln[len("event:") :].strip() or "message"
        elif ln.startswith("data:"):
            data_parts.append(ln[len("data:") :].strip())
    if data_parts:
        raw_data = "".join(data_parts)
        try:
            parsed = json.loads(raw_data)
            data = parsed.get("data") if isinstance(parsed, dict) else parsed
        except Exception:
            data = {"raw": raw_data}
        yield event_name, data


def _handle_stream_request(
    client: TestClient,
    req: Dict[str, Any],
    pipe,
    write_lock: threading.Lock,
    cancel_event: threading.Event,
    active_streams: Dict[str, threading.Event],
    active_streams_lock: threading.Lock,
) -> None:
    req_id = str(req.get("id") or "")
    method = str(req.get("method") or "GET").upper()
    url = str(req.get("url") or "")
    body = req.get("body")

    try:
        with client.stream(method, url, json=body) as resp:
            if resp.status_code >= 400:
                detail = ""
                try:
                    obj = resp.json()
                    detail = str(obj.get("detail") if isinstance(obj, dict) else obj)
                except Exception:
                    detail = resp.text
                _write_frame(
                    pipe,
                    {
                        "id": req_id,
                        "kind": "error",
                        "status": resp.status_code,
                        "message": detail or f"HTTP {resp.status_code}",
                    },
                    write_lock,
                )
                return

            for ev, data in _iter_sse_frames(resp.iter_lines()):
                if cancel_event.is_set():
                    _write_frame(pipe, {"id": req_id, "kind": "stream_end", "cancelled": True}, write_lock)
                    return
                _write_frame(
                    pipe,
                    {
                        "id": req_id,
                        "kind": "stream_event",
                        "event": ev,
                        "data": data,
                    },
                    write_lock,
                )
            _write_frame(pipe, {"id": req_id, "kind": "stream_end"}, write_lock)
    except Exception as exc:
        _write_frame(pipe, {"id": req_id, "kind": "error", "message": str(exc)}, write_lock)
    finally:
        with active_streams_lock:
            active_streams.pop(req_id, None)


def _start_stream_thread(
    client: TestClient,
    req: Dict[str, Any],
    pipe,
    write_lock: threading.Lock,
    active_streams: Dict[str, threading.Event],
    active_streams_lock: threading.Lock,
) -> None:
    req_id = str(req.get("id") or "")
    cancel_event = threading.Event()
    with active_streams_lock:
        active_streams[req_id] = cancel_event
    t = threading.Thread(
        target=_handle_stream_request,
        args=(client, req, pipe, write_lock, cancel_event, active_streams, active_streams_lock),
        daemon=True,
    )
    t.start()


def _cancel_stream(
    req_id: str,
    pipe,
    write_lock: threading.Lock,
    active_streams: Dict[str, threading.Event],
    active_streams_lock: threading.Lock,
) -> None:
    with active_streams_lock:
        ev = active_streams.get(req_id)
    if ev:
        ev.set()
    else:
            _write_frame(
                pipe,
                {
                    "id": req_id,
                "kind": "error",
                "message": "stream not found",
                },
            write_lock,
            )


def _worker_loop(pipe_path: str) -> int:
    with TestClient(app) as client:
        # wait until main process pipe server is ready
        while True:
            try:
                pipe = open(pipe_path, "r+b", buffering=0)
                break
            except FileNotFoundError:
                time.sleep(0.05)
                continue
            except OSError:
                time.sleep(0.05)
                continue

        with pipe:
            read_fp = pipe
            write_lock = threading.Lock()
            active_streams: Dict[str, threading.Event] = {}
            active_streams_lock = threading.Lock()
            while True:
                raw = read_fp.readline()
                if not raw:
                    return 0
                try:
                    req = json.loads(raw.decode("utf-8"))
                except Exception as exc:
                    _write_frame(pipe, {"kind": "error", "message": f"bad request frame: {exc}"}, write_lock)
                    continue

                req_id = str(req.get("id") or "")
                op = str(req.get("op") or "json")
                method = str(req.get("method") or "GET").upper()
                url = str(req.get("url") or "")
                body = req.get("body")
                try:
                    if op == "stream":
                        _start_stream_thread(client, req, pipe, write_lock, active_streams, active_streams_lock)
                        continue
                    if op == "stream_cancel":
                        _cancel_stream(req_id, pipe, write_lock, active_streams, active_streams_lock)
                        continue

                    resp = client.request(method, url, json=body)
                    out: Any
                    try:
                        out = resp.json()
                    except Exception:
                        out = {"raw": resp.text}
                    _write_frame(
                        pipe,
                        {
                            "id": req_id,
                            "kind": "json_result",
                            "status": resp.status_code,
                            "ok": bool(resp.status_code < 400),
                            "data": out,
                        },
                        write_lock,
                    )
                except Exception as exc:
                    _write_frame(
                        pipe,
                        {
                            "id": req_id,
                            "kind": "error",
                            "message": str(exc),
                        },
                        write_lock,
                    )


def main() -> int:
    pipe_path = str(os.getenv("NOVEL_AGENT_PIPE_PATH") or "").strip()
    if not pipe_path:
        sys.stderr.write("NOVEL_AGENT_PIPE_PATH is required\n")
        return 2
    return _worker_loop(pipe_path)


if __name__ == "__main__":
    raise SystemExit(main())
