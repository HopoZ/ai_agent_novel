# `tests/` — 各文件职责

| 文件 | 作用 |
|------|------|
| `test_time_slot_infer.py` | `infer_time_slot` 与锚点相关语义（after/before 区间等） |

**修改 `infer_time_slot` 或 `server._infer_time_slot` 时的联动**见 [`../ARCHITECTURE.md`](../ARCHITECTURE.md) 第 9 节。

运行：

```bash
python -m pytest tests/ -q
```
