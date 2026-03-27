from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator


class NovelMeta(BaseModel):
    model_config = ConfigDict(extra="allow")
    novel_id: str
    # 前端展示用的小说名（uuid 保持为内部编号）
    novel_title: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # 当前状态是否已经由 LLM 初始化（填充完整人物/世界）
    initialized: bool = False
    current_chapter_index: int = 0

    # 本小说使用的 lorebook 设定 tag（来自 settings/*.md 文件名）
    lore_tags: List[str] = Field(default_factory=list)


class CharacterPresence(BaseModel):
    model_config = ConfigDict(extra="allow")
    character_id: str
    role_in_scene: Optional[str] = None
    status_at_scene: Optional[str] = None


class CharacterState(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    # 兼容 LLM 常见输出：{"id": "..."} 或 {"character_id": "..."}
    character_id: str = Field(alias="id")
    description: Optional[str] = None
    current_location: Optional[str] = None
    alive: Optional[bool] = None

    # 关系/动机/已知事实保持“总结型”，避免状态膨胀
    relationships: Dict[str, str] = Field(default_factory=dict)
    goals: List[str] = Field(default_factory=list)
    known_facts: List[str] = Field(default_factory=list)

    # 可选：当模型需要保留更长的推演链时使用
    history: List[str] = Field(default_factory=list)


class TimelineEvent(BaseModel):
    model_config = ConfigDict(extra="allow")
    time_slot: str
    chapter_index: Optional[int] = None
    summary: str


class WorldState(BaseModel):
    model_config = ConfigDict(extra="allow")
    # 关键规则/已确认结论（从设定里提炼到“不会再争论”的版本）
    key_rules: Dict[str, str] = Field(default_factory=dict)
    factions: Dict[str, str] = Field(default_factory=dict)

    timeline: List[TimelineEvent] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)

    @field_validator("timeline", mode="before")
    @classmethod
    def _coerce_timeline(cls, v):
        # 兼容 LLM 输出：timeline: ["两年前：xxx", "今日：yyy"] 或 timeline: [{...}, ...]
        if v is None:
            return []
        if isinstance(v, list) and (len(v) == 0 or isinstance(v[0], str)):
            out = []
            for s in v:
                if not isinstance(s, str):
                    continue
                if "：" in s:
                    left, right = s.split("：", 1)
                elif ":" in s:
                    left, right = s.split(":", 1)
                else:
                    left, right = "未标注时间", s
                out.append({"time_slot": left.strip() or "未标注时间", "summary": right.strip()})
            return out
        return v


class ContinuityState(BaseModel):
    model_config = ConfigDict(extra="allow")
    # 你要写的时间段/时间线阶段（自由文本或半结构化都可以）
    time_slot: str

    # 谁在这一段出现/发生作用（用于稳定连续性与 POV）
    who_is_present: List[CharacterPresence] = Field(default_factory=list)

    # POV（如果你希望稳定文风，这个字段很关键）
    pov_character_id: Optional[str] = None

    current_location: Optional[str] = None

    @field_validator("who_is_present", mode="before")
    @classmethod
    def _coerce_who_is_present(cls, v):
        # 兼容 LLM 输出：who_is_present: ["虚宇", "苏瑶"] 或 [{"character_id":...}, ...]
        if v is None:
            return []
        if isinstance(v, list) and (len(v) == 0 or isinstance(v[0], str)):
            out = []
            for s in v:
                if isinstance(s, str):
                    out.append({"character_id": s})
            return out
        return v


class NovelState(BaseModel):
    model_config = ConfigDict(extra="allow")
    meta: NovelMeta
    continuity: ContinuityState

    characters: List[CharacterState] = Field(default_factory=list)
    world: WorldState = Field(default_factory=WorldState)

    # 用于长期稳定：最近 N 章的压缩摘要
    recent_summaries: List[str] = Field(default_factory=list)

    @field_validator("characters", mode="before")
    @classmethod
    def _coerce_characters(cls, v):
        # 兼容 LLM 输出：characters: [{"id": "...", ...}, ...]
        if v is None:
            return []
        return v


class Beat(BaseModel):
    beat_title: str
    summary: str
    time_slot: Optional[str] = None


class ChapterPlan(BaseModel):
    model_config = ConfigDict(extra="allow")
    chapter_index: int
    time_slot: str
    pov_character_id: Optional[str]
    who_is_present: List[CharacterPresence] = Field(default_factory=list)
    beats: List[Beat] = Field(default_factory=list)

    # 本章结束后要落盘的“完整世界状态”
    next_state: NovelState

    @field_validator("who_is_present", mode="before")
    @classmethod
    def _coerce_plan_who(cls, v):
        # 同 ContinuityState 的兼容策略
        if v is None:
            return []
        if isinstance(v, list) and (len(v) == 0 or isinstance(v[0], str)):
            return [{"character_id": s} for s in v if isinstance(s, str)]
        return v


class ChapterRecord(BaseModel):
    chapter_index: int
    # 用户可选的章节预设名，用于生成唯一章节文件名
    chapter_preset_name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    time_slot: str
    pov_character_id: Optional[str]
    who_is_present: List[CharacterPresence] = Field(default_factory=list)

    # beats 与正文分离，方便后续只做规划或修订
    beats: List[Beat] = Field(default_factory=list)
    content: str

    # 记录 token 使用，便于后续评测与预算控制
    usage_metadata: Dict[str, Any] = Field(default_factory=dict)

