from __future__ import annotations

from datetime import UTC, datetime

from agents.persistence.graph_tables import (
    load_character_relations,
    load_event_relations,
    replace_chapter_belongs_for_chapter,
    save_character_relations,
    save_event_relations,
)
from agents.persistence.storage import load_chapter, load_state, save_chapter, save_state
from agents.state.state_models import ChapterRecord, CharacterState, NovelState, TimelineEvent
from webapp.backend.routes import graph, novels
from webapp.backend.schemas import CreateNovelRequest, GraphBatchDeleteEdgesRequest


def test_batch_delete_edges_by_type_and_node_filter(monkeypatch, tmp_path):
    monkeypatch.setenv("NOVEL_AGENT_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("NOVEL_AGENT_OUTPUTS_DIR", str(tmp_path / "outputs"))

    created = novels.create_novel(
        CreateNovelRequest(
            novel_title="图谱批量删边测试",
            start_time_slot="第一幕",
            pov_character_id="hero",
            lore_tags=[],
        )
    )
    novel_id = str(created["novel_id"])
    st = load_state(novel_id)
    assert st is not None

    st.meta.initialized = True
    st.characters = [
        CharacterState(character_id="hero", name="主角", description="主角"),
        CharacterState(character_id="ally", name="同伴", description="同伴"),
    ]
    st.world.timeline = [
        TimelineEvent(event_id="ev:timeline:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", time_slot="第一幕", summary="开场"),
        TimelineEvent(event_id="ev:timeline:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", time_slot="第二幕", summary="推进"),
    ]
    save_state(novel_id, st)

    chap = ChapterRecord(
        chapter_index=1,
        created_at=datetime.now(UTC),
        timeline_event_id="ev:timeline:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        time_slot="第一幕",
        pov_character_id="hero",
        who_is_present=[{"character_id": "hero"}],
        beats=[],
        content="测试正文",
    )
    save_chapter(novel_id, chap, chapter_preset_name=None)
    st2 = load_state(novel_id)
    assert st2 is not None
    replace_chapter_belongs_for_chapter(novel_id, st2, chap)

    save_character_relations(
        novel_id,
        [{"source": "char:hero", "target": "char:ally", "label": "同盟", "kind": "relationship"}],
    )
    save_event_relations(
        novel_id,
        [
            {"source": "char:hero", "target": "ev:chapter:1", "label": "出场", "kind": "appear"},
            {
                "source": "ev:timeline:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "target": "ev:timeline:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "label": "时间推进",
                "kind": "timeline_next",
            },
            {
                "source": "ev:chapter:1",
                "target": "ev:timeline:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "label": "属于事件",
                "kind": "chapter_belongs",
            },
        ],
    )

    res1 = graph.batch_delete_graph_edges(
        novel_id,
        GraphBatchDeleteEdgesRequest(edge_types=["relationship", "timeline_next"]),
    )
    assert int(res1.get("deleted_by_type", {}).get("relationship", 0)) == 1
    assert int(res1.get("deleted_by_type", {}).get("timeline_next", 0)) == 1
    assert load_character_relations(novel_id) == []
    assert not any(str(r.get("kind", "")).lower() == "timeline_next" for r in load_event_relations(novel_id))

    res2 = graph.batch_delete_graph_edges(
        novel_id,
        GraphBatchDeleteEdgesRequest(
            edge_types=["chapter_belongs"],
            source_node_type="chapter_event",
            target_node_type="timeline_event",
        ),
    )
    assert int(res2.get("deleted_by_type", {}).get("chapter_belongs", 0)) >= 1
    chapter_after = load_chapter(novel_id, 1)
    assert chapter_after is not None
    assert not chapter_after.timeline_event_id
