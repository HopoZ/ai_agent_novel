"""
状态模型（Pydantic）。完整架构与 import 约定见 `agents/README.md`。

压缩与合并请用子模块（避免与 persistence 循环导入）：
- `from agents.state.state_compactor import compact_state_for_prompt, ...`
- `from agents.state.state_merge import merge_state`
"""

from .state_models import (
    Beat,
    ChapterPlan,
    ChapterRecord,
    CharacterPresence,
    CharacterState,
    ContinuityState,
    EventPlan,
    EventPlanRecord,
    NovelMeta,
    NovelState,
    TimelineEvent,
    WorldState,
)

__all__ = [
    "Beat",
    "ChapterPlan",
    "ChapterRecord",
    "CharacterPresence",
    "CharacterState",
    "ContinuityState",
    "EventPlan",
    "EventPlanRecord",
    "NovelMeta",
    "NovelState",
    "TimelineEvent",
    "WorldState",
]
