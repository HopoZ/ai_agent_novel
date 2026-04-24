from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CreateNovelRequest(BaseModel):
    novel_title: Optional[str] = None
    start_time_slot: Optional[str] = None
    pov_character_id: Optional[str] = None
    initial_user_task: Optional[str] = None
    lore_tags: Optional[List[str]] = None
    auto_generate_lore: bool = True
    auto_lore_brief: Optional[str] = None


class AutoLoreRegenerateRequest(BaseModel):
    brief: Optional[str] = None
    overwrite: bool = True


class NovelUpdateRequest(BaseModel):
    novel_title: str


class NovelTagsUpdateRequest(BaseModel):
    lore_tags: List[str] = Field(default_factory=list)


class BuildLoreSummaryRequest(BaseModel):
    tags: List[str] = Field(default_factory=list)
    force: bool = False


class LoreTagCreateRequest(BaseModel):
    tag: str
    content: str = ""
    overwrite: bool = False


class LoreTagRenameRequest(BaseModel):
    old_tag: str
    new_tag: str


class LoreTagDeleteRequest(BaseModel):
    tag: str


class LoreTagUpdateContentRequest(BaseModel):
    tag: str
    content: str = ""


class LoreTagBatchDeleteRequest(BaseModel):
    tags: List[str] = Field(default_factory=list)


class LoreTagBatchReplacePrefixRequest(BaseModel):
    tags: List[str] = Field(default_factory=list)
    old_prefix: str = ""
    new_prefix: str = ""


class RunModeRequest(BaseModel):
    mode: str = Field(
        description=(
            "init_state | plan_only | write_chapter | revise_chapter | "
            "expand_chapter | optimize_suggestions"
        )
    )
    user_task: str
    # 不建议前端显式指定 chapter_index（现实中会有重排/插入等需求）
    # 保留这个字段仅用于兼容/内部调试
    chapter_index: Optional[int] = None
    chapter_preset_name: Optional[str] = Field(
        default=None, description="章节预设名（用于生成唯一章节 JSON 文件名）"
    )
    # 区间语义（推荐）：插入在 after 之后、before 之前
    insert_after_id: Optional[str] = Field(
        default=None, description="插入在该事件之后（ev:timeline:X / ev:chapter:Y）"
    )
    insert_before_id: Optional[str] = Field(
        default=None, description="插入在该事件之前（ev:timeline:X / ev:chapter:Y）"
    )
    # 兼容字段（已废弃）：单锚点插入（旧前端可能还会发）
    insert_anchor_id: Optional[str] = Field(
        default=None, description="（deprecated）旧字段：单锚点 ev:timeline:X / ev:chapter:Y"
    )
    # 新时序语义：章节归属事件（已有/新建）
    existing_event_id: Optional[str] = Field(
        default=None, description="章节归属的已有事件（ev:timeline:X）"
    )
    new_event_time_slot: Optional[str] = Field(
        default=None, description="新建事件的 time_slot"
    )
    new_event_summary: Optional[str] = Field(
        default=None, description="新建事件的 summary"
    )
    new_event_prev_id: Optional[str] = Field(
        default=None,
        description="新建事件的上一事件（ev:timeline:X）；留空则不写前置 timeline_next，不推断",
    )
    new_event_next_id: Optional[str] = Field(
        default=None,
        description="新建事件的下一事件（ev:timeline:X）；留空则不写后置 timeline_next，不推断",
    )
    time_slot_override: Optional[str] = None
    # 新字段：主视角可多选（表示与本章最相关核心人物）
    pov_character_ids_override: Optional[List[str]] = None
    # 兼容旧字段：单 POV
    pov_character_id_override: Optional[str] = None
    # 配角设定（前端“快速多选角色”）
    supporting_character_ids: Optional[List[str]] = None
    current_map: Optional[str] = Field(
        default=None,
        description="当前地图/场景空间说明（可选，会拼入发给模型的 user_task 约束）",
    )
    lore_tags: Optional[List[str]] = None
    # 单次请求 LLM 采样参数（留空则使用服务端默认，见 agents/novel/llm_client.init_deepseek_chat）
    llm_temperature: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="temperature；规划/写作/初始化等均生效",
    )
    llm_top_p: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="top_p（nucleus sampling）",
    )
    llm_max_tokens: Optional[int] = Field(
        default=None,
        ge=1,
        le=200000,
        description="max_tokens（单次生成上限，依供应商支持为准）",
    )
    structure_card: Optional[Dict[str, Any]] = Field(
        default=None,
        description="章节结构卡（goal/conflict/turning_point/foreshadow_payoff/event_binding）",
    )
    structure_risk_ack: bool = Field(
        default=False,
        description="当结构卡未满足最小要求时，是否确认“继续生成（风险）”",
    )
    shadow_director_guidance: Optional[Dict[str, Any]] = Field(
        default=None,
        description="影子编导自动建议（冲突类型/伏笔回收/推荐配角等）",
    )


# --- 图谱 API 请求体（原 server.py 内联模型） ---


class GraphNodePatchRequest(BaseModel):
    node_id: str
    patch: Dict[str, Any]


class GraphNodeCreateRequest(BaseModel):
    node_type: str  # character | timeline_event | faction
    character_id: Optional[str] = None
    description: Optional[str] = None
    time_slot: Optional[str] = None
    summary: Optional[str] = None
    faction_name: Optional[str] = None


class GraphRelationshipRequest(BaseModel):
    source: str
    target: str
    label: str = ""
    op: str = "set"  # set | delete


class TimelineNeighborsRequest(BaseModel):
    node_id: str
    prev_source: Optional[str] = None
    next_target: Optional[str] = None


class GraphEdgePatchRequest(BaseModel):
    edge_type: str  # relationship | appear | timeline_next | chapter_belongs
    source: str
    target: str
    new_source: Optional[str] = None
    new_target: Optional[str] = None
    label: Optional[str] = None
    op: str = "set"  # set | delete


class ApiKeyUpdateRequest(BaseModel):
    api_key: str = ""
    provider: Optional[str] = None  # deepseek | openai_compatible
    base_url: Optional[str] = None
    model: Optional[str] = None


class ApiModelListRequest(BaseModel):
    provider: Optional[str] = None  # deepseek | openai_compatible
    api_key: str = ""
    base_url: Optional[str] = None
    force_refresh: bool = False


class ApiConnectionTestRequest(BaseModel):
    provider: Optional[str] = None  # deepseek | openai_compatible
    api_key: str = ""
    base_url: Optional[str] = None
    model: Optional[str] = None

