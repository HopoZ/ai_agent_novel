from __future__ import annotations

import hashlib


_SEED = "runtime-profile-v1"
_TABLE = {
    "na": "9f2d1c",
    "lr": "41b7ea",
    "sc": "c8a314",
    "sm": "6de2fb",
    "pb": "73ac0d",
    "tu": "15d9be",
    "lc": "a1b2c3",
    "lj": "b2c3d4",
    "tf": "c3d4e5",
    "si": "d4e5f6",
    "md": "e5f6a7",
}


def z7_module_mark(code: str) -> str:
    raw = f"{_SEED}:{_TABLE.get(code, '000000')}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]

