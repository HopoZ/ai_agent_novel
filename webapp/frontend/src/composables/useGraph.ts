import type { InjectionKey, Ref } from "vue";
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import * as echarts from "echarts";
import { apiJson } from "../api/client";

export function useGraph(novelId: Ref<string>) {
  const graphView = ref<"people" | "events" | "mixed">("mixed");
  const graphFullscreenVisible = ref(false);
  function onGraphViewChange(v: "people" | "events" | "mixed") {
    graphView.value = v;
  }
  const graphViewLabel = computed(() => {
    if (graphView.value === "people") return "人物关系网";
    if (graphView.value === "events") return "剧情事件网";
    return "混合网";
  });
  const graphLoading = ref(false);
  const graphEl = ref<HTMLDivElement | null>(null);
  let graphChart: echarts.ECharts | null = null;
  const graphData = ref<{ nodes: unknown[]; edges: unknown[] } | null>(null);
  function onGraphRef(el: unknown) {
    graphEl.value = el as HTMLDivElement | null;
  }

  const graphEditVisible = ref(false);
  const graphEditNode = ref<Record<string, unknown> | null>(null);
  const graphEditEdge = ref<Record<string, unknown> | null>(null);
  const graphCharDesc = ref("");
  const graphCharGoals = ref("");
  const graphCharFacts = ref("");
  const graphFacDesc = ref("");
  const graphTlSlot = ref("");
  const graphTlSummary = ref("");
  /** 章节节点归属的时间线事件 id（可空 = 仅按 time_slot 弱对齐） */
  const graphChapterTimelineEventId = ref("");
  const timelinePrevDraft = ref("");
  const timelineNextDraft = ref("");
  const relTarget = ref("");
  const relLabel = ref("");
  const edgeRelLabel = ref("");
  const edgeSourceDraft = ref("");
  const edgeTargetDraft = ref("");

  const graphCreateVisible = ref(false);
  const graphCreateSubmitting = ref(false);
  const graphCreateType = ref<"character" | "timeline_event" | "faction">("timeline_event");
  const graphCreateCharId = ref("");
  const graphCreateCharDesc = ref("");
  const graphCreateTlSlot = ref("");
  const graphCreateTlSummary = ref("");
  const graphCreateFacName = ref("");
  const graphCreateFacDesc = ref("");

  /** 全屏图谱搜索：匹配 id / 展示名 / 类型 / 节点 data 内字符串 */
  const graphSearchQuery = ref("");
  const graphSearchFocusIdx = ref(0);
  const graphLastCreatedNodeId = ref("");
  const graphNodeTypeFilters = ref<string[]>([
    "character",
    "timeline_event",
    "chapter_event",
    "faction",
  ]);
  const graphEdgeTypeFilters = ref<string[]>([
    "relationship",
    "appear",
    "timeline_next",
    "chapter_belongs",
  ]);
  const graphOnlyIsolatedNodes = ref(false);

  function graphNodeSearchBlob(n: Record<string, unknown>): string {
    const parts: string[] = [
      String(n.id ?? ""),
      typeof n.label === "string" ? n.label : "",
      String(n.type ?? ""),
    ];
    const d = n.data;
    if (d && typeof d === "object" && !Array.isArray(d)) {
      for (const v of Object.values(d as Record<string, unknown>)) {
        if (typeof v === "string") parts.push(v);
        else if (Array.isArray(v)) parts.push(v.map((x) => String(x)).join(" "));
        else if (v != null) parts.push(JSON.stringify(v));
      }
    }
    return parts.join(" ").toLowerCase();
  }

  function graphNodeMatchesQuery(n: Record<string, unknown>, q: string): boolean {
    const t = q.trim().toLowerCase();
    if (!t) return true;
    const terms = t.split(/\s+/).map((x) => x.trim()).filter(Boolean);
    if (!terms.length) return true;
    const blob = graphNodeSearchBlob(n);
    return terms.every((term) => blob.includes(term));
  }

  const graphSearchMatchCount = computed(() => {
    const payload = graphData.value;
    const q = graphSearchQuery.value.trim();
    if (!payload?.nodes?.length || !q) return 0;
    return (payload.nodes as Record<string, unknown>[]).filter((n) => graphNodeMatchesQuery(n, q)).length;
  });

  const graphStats = computed(() => {
    const payload = graphData.value;
    const nodes = (payload?.nodes || []) as Record<string, unknown>[];
    const edges = (payload?.edges || []) as Record<string, unknown>[];
    const nodeByType: Record<string, number> = {
      character: 0,
      timeline_event: 0,
      chapter_event: 0,
      faction: 0,
      other: 0,
    };
    const edgeByType: Record<string, number> = {
      relationship: 0,
      appear: 0,
      timeline_next: 0,
      chapter_belongs: 0,
      other: 0,
    };
    for (const n of nodes) {
      const t = String(n.type || "");
      if (t in nodeByType) nodeByType[t] += 1;
      else nodeByType.other += 1;
    }
    for (const e of edges) {
      const t = String(e.type || "");
      if (t in edgeByType) edgeByType[t] += 1;
      else edgeByType.other += 1;
    }
    return { nodeTotal: nodes.length, edgeTotal: edges.length, nodeByType, edgeByType };
  });

  const graphCharacterNodeIds = computed(() => {
    const nodes = graphData.value?.nodes || [];
    return nodes
      .filter(
        (n: unknown) =>
          n &&
          typeof n === "object" &&
          (n as { type?: string; id?: string }).type === "character" &&
          typeof (n as { id?: string }).id === "string" &&
          String((n as { id: string }).id).startsWith("char:")
      )
      .map((n: unknown) => String((n as { id: string }).id).slice("char:".length))
      .filter(Boolean);
  });

  const relationTargetOptions = computed(() => {
    const node = graphEditNode.value;
    const sourceId = String(node?.id || "");
    return graphCharacterNodeIds.value.filter((cid) => `char:${cid}` !== sourceId);
  });

  const graphTimelineOptions = computed(() => {
    const nodes = graphData.value?.nodes || [];
    return nodes
      .filter(
        (n: unknown) =>
          n &&
          typeof n === "object" &&
          (n as { type?: string; id?: string }).type === "timeline_event" &&
          typeof (n as { id?: string }).id === "string" &&
          String((n as { id: string }).id).startsWith("ev:timeline:")
      )
      .map((n: unknown) => ({
        id: String((n as { id: string }).id),
        label: String((n as { label?: string }).label || (n as { id: string }).id),
      }));
  });

  const graphChapterNodeIds = computed(() => {
    const nodes = graphData.value?.nodes || [];
    return nodes
      .filter(
        (n: unknown) =>
          n &&
          typeof n === "object" &&
          (n as { type?: string; id?: string }).type === "chapter_event" &&
          typeof (n as { id?: string }).id === "string" &&
          String((n as { id: string }).id).startsWith("ev:chapter:")
      )
      .map((n: unknown) => String((n as { id: string }).id))
      .filter(Boolean);
  });

  function nid() {
    return (novelId.value || "").trim();
  }

  function openGraphEditor(node: Record<string, unknown>) {
    graphEditEdge.value = null;
    graphEditNode.value = node;
    graphEditVisible.value = true;
    const data = (node?.data as Record<string, unknown>) || {};
    const nodeType = String(node?.type || "");
    if (nodeType === "character") {
      graphCharDesc.value = String(data?.description || "");
      graphCharGoals.value = Array.isArray(data?.goals)
        ? (data.goals as unknown[]).join("\n")
        : String(data?.goals || "");
      graphCharFacts.value = Array.isArray(data?.known_facts)
        ? (data.known_facts as unknown[]).join("\n")
        : String(data?.known_facts || "");
    } else if (nodeType === "faction") {
      graphFacDesc.value = String(data?.description || "");
    } else if (nodeType === "timeline_event") {
      graphTlSlot.value = String(data?.time_slot || "");
      graphTlSummary.value = String(data?.summary || "");
      const edges = (graphData.value?.edges || []).filter(
        (e: unknown) => (e && typeof e === "object" ? (e as { type?: string }).type : "") === "timeline_next"
      );
      const nodeIdStr = String(node?.id || "");
      const incoming = edges.find(
        (e: unknown) => String((e as { target?: string })?.target || "") === nodeIdStr
      ) as { source?: string } | undefined;
      const outgoing = edges.find(
        (e: unknown) => String((e as { source?: string })?.source || "") === nodeIdStr
      ) as { target?: string } | undefined;
      timelinePrevDraft.value = String(incoming?.source || "");
      timelineNextDraft.value = String(outgoing?.target || "");
    } else if (nodeType === "chapter_event") {
      graphChapterTimelineEventId.value = String(data?.timeline_event_id || "").trim();
    }
    relTarget.value = "";
    relLabel.value = "";
  }

  async function saveTimelineNeighbors() {
    const id = nid();
    const node = graphEditNode.value;
    if (!id || !node || String(node.type) !== "timeline_event") return;
    const nodeIdStr = String(node.id || "");
    if (!nodeIdStr.startsWith("ev:timeline:")) {
      ElMessage.error("当前节点不是可编辑的时间线事件。");
      return;
    }
    if (timelinePrevDraft.value && timelinePrevDraft.value === nodeIdStr) {
      ElMessage.error("上一跳不能指向自己。");
      return;
    }
    if (timelineNextDraft.value && timelineNextDraft.value === nodeIdStr) {
      ElMessage.error("下一跳不能指向自己。");
      return;
    }

    const newPrev = (timelinePrevDraft.value || "").trim();
    const newNext = (timelineNextDraft.value || "").trim();
    await apiJson(`/api/novels/${encodeURIComponent(id)}/graph/timeline-neighbors`, "PATCH", {
      node_id: nodeIdStr,
      prev_source: newPrev || "",
      next_target: newNext || "",
    });

    ElMessage.success("已保存事件节点的上/下关系");
    await loadGraph();
  }

  async function saveChapterEventTimeline() {
    const id = nid();
    const node = graphEditNode.value;
    if (!id || !node || String(node.type) !== "chapter_event") return;
    const nodeIdStr = String(node.id || "");
    if (!nodeIdStr.startsWith("ev:chapter:")) {
      ElMessage.error("当前节点不是章节事件节点。");
      return;
    }
    const teid = (graphChapterTimelineEventId.value || "").trim();
    await apiJson(`/api/novels/${encodeURIComponent(id)}/graph/node`, "PATCH", {
      node_id: nodeIdStr,
      patch: { timeline_event_id: teid || null },
    });
    ElMessage.success("已保存章节归属事件");
    await loadGraph();
    if (graphFullscreenVisible.value) renderGraph();
  }

  function openGraphEdgeEditor(edge: Record<string, unknown>) {
    graphEditNode.value = null;
    graphEditEdge.value = edge;
    graphEditVisible.value = true;
    edgeRelLabel.value = String(
      edge?.rel_label || (typeof edge?.label === "string" ? edge.label : "")
    );
    edgeSourceDraft.value = String(edge?.source || "");
    edgeTargetDraft.value = String(edge?.target || "");
  }

  async function saveGraphNodePatch() {
    const id = nid();
    if (!id || !graphEditNode.value) return;
    const node = graphEditNode.value;
    let patch: Record<string, unknown> = {};
    const nodeType = String(node.type || "");
    if (nodeType === "character") {
      patch = {
        description: graphCharDesc.value,
        goals: graphCharGoals.value,
        known_facts: graphCharFacts.value,
      };
    } else if (nodeType === "faction") {
      patch = { description: graphFacDesc.value };
    } else if (nodeType === "timeline_event") {
      patch = { time_slot: graphTlSlot.value, summary: graphTlSummary.value };
    } else {
      ElMessage.warning("该节点类型暂不支持保存。");
      return;
    }
    await apiJson(`/api/novels/${encodeURIComponent(id)}/graph/node`, "PATCH", {
      node_id: node.id,
      patch,
    });
    ElMessage.success("已保存节点修改");
    await loadGraph();
  }

  async function setRelationship() {
    const id = nid();
    const node = graphEditNode.value;
    if (!id || !node || String(node.type) !== "character") return;
    const srcId = String(node.id || "");
    const tgtId = (relTarget.value || "").trim();
    const label = (relLabel.value || "").trim();
    if (!tgtId || !label) {
      ElMessage.error("请选择 target 并填写关系 label。");
      return;
    }
    await apiJson(`/api/novels/${encodeURIComponent(id)}/graph/relationship`, "POST", {
      source: srcId,
      target: `char:${tgtId}`,
      label,
      op: "set",
    });
    ElMessage.success("已更新关系");
    await loadGraph();
  }

  async function deleteRelationship() {
    const id = nid();
    const node = graphEditNode.value;
    if (!id || !node || String(node.type) !== "character") return;
    const srcId = String(node.id || "");
    const tgtId = (relTarget.value || "").trim();
    if (!tgtId) {
      ElMessage.error("请选择要删除的 target。");
      return;
    }
    await apiJson(`/api/novels/${encodeURIComponent(id)}/graph/relationship`, "POST", {
      source: srcId,
      target: `char:${tgtId}`,
      label: "",
      op: "delete",
    });
    ElMessage.success("已删除关系");
    await loadGraph();
  }

  async function saveEdgeRelationship() {
    const id = nid();
    const e = graphEditEdge.value;
    if (!id || !e) return;
    const source = String(e.source || "");
    const target = String(e.target || "");
    const new_source = (edgeSourceDraft.value || source).trim();
    const new_target = (edgeTargetDraft.value || target).trim();
    const label = (edgeRelLabel.value || "").trim();
    const edge_type = String(e.type || "relationship");
    if (!new_source) {
      ElMessage.error("source 不能为空。");
      return;
    }
    if (edge_type.toLowerCase() !== "timeline_next" && !new_target) {
      ElMessage.error("target 不能为空。");
      return;
    }
    if (new_source && new_target && new_source === new_target) {
      ElMessage.error("source 与 target 不能相同。");
      return;
    }
    if (edge_type.toLowerCase() === "relationship" && !label) {
      ElMessage.error("请先填写关系 label。");
      return;
    }
    await apiJson(`/api/novels/${encodeURIComponent(id)}/graph/edge`, "PATCH", {
      edge_type,
      source,
      target,
      new_source,
      new_target,
      label,
      op: "set",
    });
    ElMessage.success("已保存边修改");
    await loadGraph();
  }

  async function deleteEdgeRelationship() {
    const id = nid();
    const e = graphEditEdge.value;
    if (!id || !e) return;
    const source = String(e.source || "");
    const target = String(e.target || "");
    const edge_type = String(e.type || "relationship");
    await apiJson(`/api/novels/${encodeURIComponent(id)}/graph/edge`, "PATCH", {
      edge_type,
      source,
      target,
      op: "delete",
    });
    ElMessage.success("已删除边");
    await loadGraph();
  }

  function resetGraphCreateForm() {
    graphCreateCharId.value = "";
    graphCreateCharDesc.value = "";
    graphCreateTlSlot.value = "";
    graphCreateTlSummary.value = "";
    graphCreateFacName.value = "";
    graphCreateFacDesc.value = "";
  }

  function openGraphNodeCreate() {
    if (!nid()) {
      ElMessage.error("请先选择小说。");
      return;
    }
    resetGraphCreateForm();
    const v = graphView.value;
    if (v === "people") graphCreateType.value = "character";
    else if (v === "events") graphCreateType.value = "timeline_event";
    else graphCreateType.value = "character";
    graphCreateVisible.value = true;
  }

  async function submitGraphNodeCreate() {
    const id = nid();
    if (!id) return;
    const t = graphCreateType.value;
    let body: Record<string, unknown> = { node_type: t };
    if (t === "character") {
      const cid = (graphCreateCharId.value || "").trim();
      if (!cid) {
        ElMessage.error("请填写角色 ID。");
        return;
      }
      body.character_id = cid;
      body.description = (graphCreateCharDesc.value || "").trim() || null;
    } else if (t === "timeline_event") {
      const slot = (graphCreateTlSlot.value || "").trim();
      const summ = (graphCreateTlSummary.value || "").trim();
      if (!slot || !summ) {
        ElMessage.error("请填写 time_slot 与 summary。");
        return;
      }
      body.time_slot = slot;
      body.summary = summ;
    } else {
      const fn = (graphCreateFacName.value || "").trim();
      if (!fn) {
        ElMessage.error("请填写势力名称。");
        return;
      }
      body.faction_name = fn;
      body.description = (graphCreateFacDesc.value || "").trim() || "";
    }
    graphCreateSubmitting.value = true;
    try {
      const res = (await apiJson(`/api/novels/${encodeURIComponent(id)}/graph/nodes`, "POST", body)) as {
        node_id?: string;
      };
      ElMessage.success("已创建节点");
      graphLastCreatedNodeId.value = String(res?.node_id || "");
      graphCreateVisible.value = false;
      await loadGraph();
      if (graphFullscreenVisible.value) renderGraph();
    } catch (e: unknown) {
      const err = e as { message?: string };
      ElMessage.error(err?.message || String(e));
    } finally {
      graphCreateSubmitting.value = false;
    }
  }

  async function deleteCurrentGraphNode() {
    const id = nid();
    const node = graphEditNode.value;
    if (!id || !node?.id) return;
    const nodeIdStr = String(node.id || "");
    if (nodeIdStr.startsWith("ev:chapter:")) {
      ElMessage.warning("章节节点不能在图谱内删除，请使用章节/正文管理。");
      return;
    }
    try {
      await ElMessageBox.confirm(
        `确定删除节点「${nodeIdStr}」？人物会清理相关关系边与出场边；时间线删除会移除该事件 id 并清理相关边，其余事件 id 不变。`,
        "删除节点",
        { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
      );
    } catch {
      return;
    }
    try {
      await apiJson(
        `/api/novels/${encodeURIComponent(id)}/graph/nodes?node_id=${encodeURIComponent(nodeIdStr)}`,
        "DELETE",
        undefined
      );
      ElMessage.success("已删除节点");
      graphEditVisible.value = false;
      graphEditNode.value = null;
      await loadGraph();
      if (graphFullscreenVisible.value) renderGraph();
    } catch (e: unknown) {
      const err = e as { message?: string };
      ElMessage.error(err?.message || String(e));
    }
  }

  async function openGraphDialog() {
    if (!nid()) {
      ElMessage.error("请先选择/创建小说。");
      return;
    }
    graphFullscreenVisible.value = true;
    await nextTick();
    if (graphData.value) {
      renderGraph();
    } else {
      await loadGraph();
    }
    onResize();
  }

  function closeGraphDialog() {
    graphFullscreenVisible.value = false;
  }

  function onResize() {
    if (graphChart) graphChart.resize();
  }

  function typeColor(t: string) {
    if (t === "character") return "#5B8FF9";
    if (t === "chapter_event") return "#61DDAA";
    if (t === "timeline_event") return "#F6BD16";
    if (t === "faction") return "#E8684A";
    return "#A3B1BF";
  }

  function ensureGraphChart() {
    if (!graphEl.value) return;
    if (graphChart) return;
    graphChart = echarts.init(graphEl.value, undefined, { renderer: "canvas" });
    window.addEventListener("resize", onResize);
    graphChart.on("click", (params: any) => {
      const pData = params?.data;
      if (params?.dataType === "node" && pData && typeof pData === "object" && !Array.isArray(pData)) {
        openGraphEditor(pData as Record<string, unknown>);
      }
      if (params?.dataType === "edge" && pData && typeof pData === "object" && !Array.isArray(pData)) {
        openGraphEdgeEditor(pData as Record<string, unknown>);
      }
    });
  }

  function renderGraph() {
    ensureGraphChart();
    if (!graphChart) return;
    const payload = graphData.value;
    if (!payload) {
      graphChart.clear();
      return;
    }

    const qRaw = graphSearchQuery.value.trim().toLowerCase();
    const rawNodeList = (payload.nodes || []) as Record<string, unknown>[];
    const allowedNodeTypes = new Set(graphNodeTypeFilters.value);
    const filteredNodes = rawNodeList.filter((n) => allowedNodeTypes.has(String(n.type || "")));
    const nodeIdSet = new Set(filteredNodes.map((n) => String(n.id || "")));
    const allowedEdgeTypes = new Set(graphEdgeTypeFilters.value);
    const preLinks = ((payload.edges || []) as Record<string, unknown>[]).filter((e) => {
      const t = String(e.type || "");
      const sid = String(e.source || "");
      const tid = String(e.target || "");
      return allowedEdgeTypes.has(t) && nodeIdSet.has(sid) && (tid ? nodeIdSet.has(tid) : true);
    });
    const degree = new Map<string, number>();
    for (const id of nodeIdSet) degree.set(id, 0);
    for (const e of preLinks) {
      const sid = String(e.source || "");
      const tid = String(e.target || "");
      if (degree.has(sid)) degree.set(sid, (degree.get(sid) || 0) + 1);
      if (tid && degree.has(tid)) degree.set(tid, (degree.get(tid) || 0) + 1);
    }
    const shownNodes = graphOnlyIsolatedNodes.value
      ? filteredNodes.filter((n) => (degree.get(String(n.id || "")) || 0) === 0)
      : filteredNodes;
    const shownNodeIds = new Set(shownNodes.map((n) => String(n.id || "")));
    const shownLinks = preLinks.filter((e) => {
      const sid = String(e.source || "");
      const tid = String(e.target || "");
      return shownNodeIds.has(sid) && (tid ? shownNodeIds.has(tid) : true);
    });
    const matchById = new Map<string, boolean>();
    for (const n of shownNodes) {
      const id = String(n.id ?? "");
      matchById.set(id, !qRaw || graphNodeMatchesQuery(n, qRaw));
    }

    const nodes = shownNodes.map((n: Record<string, unknown>) => {
      const idStr = String(n.id ?? "");
      const match = matchById.get(idStr) !== false;
      const baseColor = typeColor(String(n.type || ""));
      const displayName =
        typeof n.label === "string" && n.label ? n.label : String(n.id ?? "");
      return {
        ...n,
        name: displayName,
        symbolSize: n.type === "character" ? 28 : n.type === "faction" ? 22 : 18,
        itemStyle: match
          ? {
              color: baseColor,
              opacity: 1,
              borderColor: qRaw ? "#b8860b" : undefined,
              borderWidth: qRaw ? 2 : 0,
            }
          : { color: baseColor, opacity: 0.06 },
        draggable: true,
        value: n.type,
      };
    });
    const links: Record<string, unknown>[] = shownLinks.map((e: Record<string, unknown>) => {
      const sid = String(e.source ?? "");
      const tid = String(e.target ?? "");
      const sm = matchById.get(sid) !== false;
      const tm = matchById.get(tid) !== false;
      const edgeLit = !qRaw || sm || tm;
      return {
        ...e,
        rel_label: typeof e?.label === "string" ? e.label : "",
        lineStyle: {
          opacity: edgeLit ? 0.65 : 0.03,
          width: edgeLit ? 1.2 : 0.6,
          curveness: 0.18,
        },
        label: {
          show: edgeLit && !!(typeof e?.label === "string" ? e.label : ""),
          formatter: typeof e?.label === "string" ? e.label : "",
        },
      };
    });

    const timelineIds = new Set(
      nodes
        .map((n: Record<string, unknown>) => String(n?.id || ""))
        .filter((id: string) => id.startsWith("ev:timeline:") && !id.includes(":draft_"))
    );
    const inCnt = new Map<string, number>();
    const outCnt = new Map<string, number>();
    for (const id of timelineIds) {
      inCnt.set(id, 0);
      outCnt.set(id, 0);
    }
    for (const e of links) {
      if (String(e?.type || "") !== "timeline_next") continue;
      const s = String(e?.source || "");
      const t = String(e?.target || "");
      if (outCnt.has(s)) outCnt.set(s, (outCnt.get(s) || 0) + 1);
      if (inCnt.has(t)) inCnt.set(t, (inCnt.get(t) || 0) + 1);
    }
    for (const n of nodes as Record<string, unknown>[]) {
      const id = String(n?.id || "");
      if (!timelineIds.has(id)) continue;
      const noPrev = (inCnt.get(id) || 0) === 0;
      const noNext = (outCnt.get(id) || 0) === 0;
      if (!(noPrev || noNext) || (noPrev && noNext)) continue;
      const flag = noPrev && !noNext ? "待定(上)" : "待定(下)";
      n.label = {
        show: true,
        position: "right",
        formatter: `{b}\n{flag|${flag}}`,
        rich: {
          flag: {
            color: "#8a5a00",
            backgroundColor: "#fff7cc",
            borderColor: "#f5c542",
            borderWidth: 1,
            borderRadius: 3,
            padding: [1, 4],
            fontSize: 11,
            lineHeight: 16,
          },
        },
      };
    }

    graphChart.setOption(
      {
        tooltip: {
          trigger: "item",
          formatter: (p: { dataType?: string; data?: Record<string, unknown> }) => {
            if (p.dataType === "node")
              return `${p.data?.type || ""}：${p.data?.label || p.data?.id}`;
            if (p.dataType === "edge") return `${p.data?.type || ""}：${p.data?.label || ""}`;
            return "";
          },
        },
        animationDurationUpdate: 300,
        series: [
          {
            type: "graph",
            layout: "force",
            roam: true,
            data: nodes,
            links,
            edgeSymbol: ["none", "arrow"],
            edgeSymbolSize: 6,
            label: { show: true, position: "right", formatter: "{b}" },
            force: { repulsion: 220, edgeLength: [60, 140], gravity: 0.06 },
          },
        ],
      },
      true
    );
    if (graphLastCreatedNodeId.value) {
      const idx = nodes.findIndex(
        (n: Record<string, unknown>) => String(n.id || "") === graphLastCreatedNodeId.value
      );
      if (idx >= 0) {
        try {
          graphChart.dispatchAction({ type: "focusNodeAdjacency", seriesIndex: 0, dataIndex: idx });
          graphChart.dispatchAction({ type: "showTip", seriesIndex: 0, dataIndex: idx });
        } catch {
          // ignore focus errors
        }
      }
      graphLastCreatedNodeId.value = "";
    }
  }

  async function loadGraph() {
    const id = nid();
    if (!id) {
      ElMessage.error("请先选择/创建小说。");
      return;
    }
    graphLoading.value = true;
    try {
      const url = `/api/novels/${encodeURIComponent(id)}/graph?view=${encodeURIComponent(graphView.value)}`;
      const res = (await apiJson(url, "GET", null)) as { nodes?: unknown[]; edges?: unknown[] };
      graphData.value = { nodes: res.nodes || [], edges: res.edges || [] };
      await nextTick();
      renderGraph();
    } catch (e: unknown) {
      const err = e as { message?: string };
      ElMessage.error("加载图谱失败：" + (err?.message || String(e)));
    } finally {
      graphLoading.value = false;
    }
  }

  watch(graphSearchQuery, () => {
    graphSearchFocusIdx.value = 0;
    if (graphFullscreenVisible.value) {
      void nextTick(() => renderGraph());
    }
  });

  watch([graphNodeTypeFilters, graphEdgeTypeFilters, graphOnlyIsolatedNodes], () => {
    if (graphFullscreenVisible.value) {
      void nextTick(() => renderGraph());
    }
  });

  watch(relTarget, (v) => {
    const node = graphEditNode.value;
    if (!node || String(node.type || "") !== "character") return;
    const source = String(node.id || "");
    const target = (v || "").trim() ? `char:${(v || "").trim()}` : "";
    if (!source || !target) return;
    const rows = (graphData.value?.edges || []) as Record<string, unknown>[];
    const hit = rows.find(
      (e) =>
        String(e.type || "").toLowerCase() === "relationship" &&
        String(e.source || "") === source &&
        String(e.target || "") === target
    );
    if (hit) {
      relLabel.value = String(hit.label || "");
    }
  });

  function focusNextGraphSearchMatch() {
    ensureGraphChart();
    if (!graphChart) return;
    const q = graphSearchQuery.value.trim().toLowerCase();
    if (!q) {
      ElMessage.info("请先输入搜索关键词。");
      return;
    }
    const payload = graphData.value;
    if (!payload?.nodes?.length) return;
    const indices: number[] = [];
    (payload.nodes as Record<string, unknown>[]).forEach((n, i) => {
      if (graphNodeMatchesQuery(n, q)) indices.push(i);
    });
    if (indices.length === 0) {
      ElMessage.info("当前图谱没有匹配的节点。");
      return;
    }
    const i = graphSearchFocusIdx.value % indices.length;
    const dataIndex = indices[i]!;
    graphSearchFocusIdx.value += 1;
    try {
      graphChart.dispatchAction({ type: "focusNodeAdjacency", seriesIndex: 0, dataIndex });
    } catch {
      ElMessage.warning("定位节点失败，可尝试缩小搜索词后重试。");
    }
  }

  function focusPrevGraphSearchMatch() {
    ensureGraphChart();
    if (!graphChart) return;
    const q = graphSearchQuery.value.trim().toLowerCase();
    if (!q) {
      ElMessage.info("请先输入搜索关键词。");
      return;
    }
    const payload = graphData.value;
    if (!payload?.nodes?.length) return;
    const indices: number[] = [];
    (payload.nodes as Record<string, unknown>[]).forEach((n, i) => {
      if (graphNodeMatchesQuery(n, q)) indices.push(i);
    });
    if (indices.length === 0) {
      ElMessage.info("当前图谱没有匹配的节点。");
      return;
    }
    const base = ((graphSearchFocusIdx.value - 2) % indices.length + indices.length) % indices.length;
    const dataIndex = indices[base]!;
    graphSearchFocusIdx.value = base + 1;
    try {
      graphChart.dispatchAction({ type: "focusNodeAdjacency", seriesIndex: 0, dataIndex });
    } catch {
      ElMessage.warning("定位节点失败，可尝试缩小搜索词后重试。");
    }
  }

  function clearGraphSearch() {
    graphSearchQuery.value = "";
    graphSearchFocusIdx.value = 0;
    void nextTick(() => renderGraph());
  }

  function resetGraphFilters() {
    graphNodeTypeFilters.value = ["character", "timeline_event", "chapter_event", "faction"];
    graphEdgeTypeFilters.value = ["relationship", "appear", "timeline_next", "chapter_belongs"];
    graphOnlyIsolatedNodes.value = false;
    void nextTick(() => renderGraph());
  }

  function exportGraphJson() {
    const id = nid();
    if (!id || !graphData.value) {
      ElMessage.warning("暂无可导出的图谱数据。");
      return;
    }
    const payload = {
      novel_id: id,
      view: graphView.value,
      exported_at: new Date().toISOString(),
      stats: graphStats.value,
      graph: graphData.value,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `graph-${id}-${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    ElMessage.success("已导出图谱 JSON。");
  }

  watch([graphView, novelId, graphFullscreenVisible], async ([, , opened]) => {
    if (!opened) return;
    await nextTick();
    await loadGraph();
  });

  onBeforeUnmount(() => {
    window.removeEventListener("resize", onResize);
    if (graphChart) {
      graphChart.dispose();
      graphChart = null;
    }
  });

  return reactive({
    graphView,
    graphFullscreenVisible,
    graphViewLabel,
    graphLoading,
    graphEl,
    onGraphRef,
    graphData,
    graphEditVisible,
    graphEditNode,
    graphEditEdge,
    graphCharDesc,
    graphCharGoals,
    graphCharFacts,
    graphFacDesc,
    graphTlSlot,
    graphTlSummary,
    graphChapterTimelineEventId,
    timelinePrevDraft,
    timelineNextDraft,
    relTarget,
    relLabel,
    edgeRelLabel,
    edgeSourceDraft,
    edgeTargetDraft,
    graphCreateVisible,
    graphCreateSubmitting,
    graphCreateType,
    graphCreateCharId,
    graphCreateCharDesc,
    graphCreateTlSlot,
    graphCreateTlSummary,
    graphCreateFacName,
    graphCreateFacDesc,
    graphNodeTypeFilters,
    graphEdgeTypeFilters,
    graphOnlyIsolatedNodes,
    graphCharacterNodeIds,
    relationTargetOptions,
    graphTimelineOptions,
    graphChapterNodeIds,
    graphStats,
    onGraphViewChange,
    openGraphDialog,
    closeGraphDialog,
    openGraphNodeCreate,
    submitGraphNodeCreate,
    openGraphEditor,
    openGraphEdgeEditor,
    saveTimelineNeighbors,
    saveChapterEventTimeline,
    saveGraphNodePatch,
    setRelationship,
    deleteRelationship,
    saveEdgeRelationship,
    deleteEdgeRelationship,
    deleteCurrentGraphNode,
    loadGraph,
    renderGraph,
    graphSearchQuery,
    graphSearchMatchCount,
    focusNextGraphSearchMatch,
    focusPrevGraphSearchMatch,
    clearGraphSearch,
    resetGraphFilters,
    exportGraphJson,
  });
}

export type GraphController = ReturnType<typeof useGraph>;
export const GRAPH_INJECTION_KEY: InjectionKey<GraphController> = Symbol("graph");
