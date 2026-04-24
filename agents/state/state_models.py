"""Pydantic 状态模型。包结构与职责见 `agents/README.md`。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

from agents._internal_marks import z7_module_mark

_MODULE_REV = z7_module_mark("md")


class NovelMeta(BaseModel):
    model_config = ConfigDict(extra="allow")
    novel_id: str
    # 前端展示用的小说名（uuid 保持为内部编号）
    novel_title: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # 当前状态是否已经由 LLM 初始化（填充完整人物/世界）
    initialized: bool = False
    current_chapter_index: int = 0

    # 本小说使用的 lorebook 设定 tag（来自 lores/**/*.md 路径 tag）
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
    # 展示名（可与 id 相同；若模型把 slug 放在 id、把中文名放在 name，此处用于界面显示）
    name: Optional[str] = None
    description: Optional[str] = None

    # 关系/动机/已知事实保持“总结型”，避免状态膨胀
    relationships: Dict[str, str] = Field(default_factory=dict)
    goals: List[str] = Field(default_factory=list)
    known_facts: List[str] = Field(default_factory=list)

    # 可选：当模型需要保留更长的推演链时使用
    history: List[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _drop_legacy_location_alive(cls, data):
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if k not in ("current_location", "alive")}
        return data


class TimelineEvent(BaseModel):
    model_config = ConfigDict(extra="allow")
    # 稳定图谱 id：ev:timeline:{uuid.hex}；顺序仍以 world.timeline 列表为准，勿用下标当 id
    event_id: Optional[str] = None
    time_slot: str
    summary: str

    @model_validator(mode="before")
    @classmethod
    def _normalize_timeline_event(cls, data):
        if not isinstance(data, dict):
            return data
        d = {k: v for k, v in data.items() if k != "chapter_index"}
        # 兼容 LLM 常用别名：time / event
        if d.get("time_slot") is None and d.get("time") is not None:
            d["time_slot"] = d["time"]
        if d.get("summary") is None and d.get("event") is not None:
            d["summary"] = d["event"]
        return d


class WorldState(BaseModel):
    model_config = ConfigDict(extra="allow")
    # 关键规则/已确认结论（从设定里提炼到“不会再争论”的版本）
    key_rules: Dict[str, str] = Field(default_factory=dict)
    factions: Dict[str, str] = Field(default_factory=dict)

    timeline: List[TimelineEvent] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)

    @field_validator("key_rules", mode="before")
    @classmethod
    def _coerce_key_rules_values_to_str(cls, v):
        # LLM 常把 key_rules 写成嵌套对象/数组；统一压成字符串以便下游 prompt 拼接
        if v is None:
            return {}
        if not isinstance(v, dict):
            return v
        out: Dict[str, str] = {}
        for k, val in v.items():
            key = str(k)
            if isinstance(val, (dict, list)):
                out[key] = json.dumps(val, ensure_ascii=False)
            elif val is None:
                out[key] = ""
            else:
                out[key] = str(val)
        return out

    @field_validator("factions", mode="before")
    @classmethod
    def _coerce_factions(cls, v):
        # 兼容 LLM 输出：factions: [{"name":"xx","description":"yy"}, ...]
        if v is None:
            return {}
        if isinstance(v, list):
            out: Dict[str, str] = {}
            for item in v:
                if isinstance(item, dict):
                    name = str(item.get("name") or "").strip()
                    desc = str(item.get("description") or "").strip()
                    if name:
                        out[name] = desc
            return out
        return v

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

    @model_validator(mode="before")
    @classmethod
    def _drop_continuity_location(cls, data):
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if k != "current_location"}
        return data


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

    @field_validator("recent_summaries", mode="before")
    @classmethod
    def _coerce_recent_summaries(cls, v):
        # 兼容 LLM 输出：recent_summaries: "..."（字符串）或 null
        if v is None:
            return []
        if isinstance(v, str):
            s = v.strip()
            return [s] if s else []
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
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # 多章可指向同一时间线事件；缺省时仍可用 time_slot 与 timeline 弱对齐
    timeline_event_id: Optional[str] = None

    time_slot: str
    pov_character_id: Optional[str]
    who_is_present: List[CharacterPresence] = Field(default_factory=list)

    # beats 与正文分离，方便后续只做规划或修订
    beats: List[Beat] = Field(default_factory=list)
    content: str

    # 记录 token 使用，便于后续评测与预算控制
    usage_metadata: Dict[str, Any] = Field(default_factory=dict)
    # 写前结构卡（C 方案）：默认自动补齐并锁定，供写后复盘与治理
    structure_card: Dict[str, Any] = Field(default_factory=dict)
    structure_card_locked: bool = False
