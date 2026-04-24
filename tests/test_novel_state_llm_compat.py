"""NovelState 对常见 LLM 别名/嵌套 key_rules 的兼容。"""

from agents.state.state_models import NovelState, TimelineEvent, WorldState


def test_timeline_event_time_event_aliases():
    ev = TimelineEvent.model_validate({"time": "当前", "event": "发生了某事"})
    assert ev.time_slot == "当前"
    assert ev.summary == "发生了某事"


def test_timeline_event_year_event_aliases():
    ev = TimelineEvent.model_validate({"year": "修真历三千二百年", "event": "林墨重生苏醒"})
    assert ev.time_slot == "修真历三千二百年"
    assert ev.summary == "林墨重生苏醒"


def test_world_key_rules_nested_coerced_to_str():
    w = WorldState.model_validate(
        {
            "key_rules": {
                "a": "plain",
                "b": ["x", "y"],
                "c": {"k": "v"},
            }
        }
    )
    assert w.key_rules["a"] == "plain"
    assert '"x"' in w.key_rules["b"] or "x" in w.key_rules["b"]
    assert "k" in w.key_rules["c"]


def test_minimal_novel_state_with_llm_style_world():
    ns = NovelState.model_validate(
        {
            "meta": {
                "novel_id": "n1",
                "novel_title": "t",
                "initialized": True,
                "current_chapter_index": 0,
            },
            "continuity": {
                "time_slot": "now",
                "pov_character_id": "p",
                "who_is_present": ["p"],
            },
            "characters": [],
            "world": {
                "key_rules": {"nested": {"x": 1}},
                "timeline": [{"time": "T", "event": "E"}],
            },
        }
    )
    assert ns.world.timeline[0].time_slot == "T"
    assert ns.world.timeline[0].summary == "E"
    assert '"x"' in ns.world.key_rules["nested"]
