<template>
  <div class="wrap">
    <h2 class="header">AI 小说创作代理（稳定写小说）</h2>

    <div class="main-layout">
      <div class="left-pane" :style="{ width: `${leftPanelWidth}px` }">
        <TagPanel
          :tags-loading="tagsLoading"
          :building-lore-summary="buildingLoreSummary"
          :on-tag-tree-ref="onTagTreeRef"
          :tag-tree-data="tagTreeData"
          :on-select-all="selectAll"
          :on-invert-select="invertSelect"
          :on-clear-select="clearSelect"
          :on-build-current-lore-summary="buildCurrentLoreSummary"
          :on-tree-check="onTreeCheck"
          :get-tag-preview="getTagPreview"
          :on-open-tag-dialog="openTagDialog"
        />
      </div>

      <div class="resize-handle" @mousedown="startResizeLeft" title="拖动调整左侧宽度"></div>

      <div class="mid-pane" :style="{ width: `${midPanelWidth}px` }">
        <MidFormPanel
          :form="form"
          :default-llm-temperature="DEFAULT_LLM_TEMPERATURE"
          :default-llm-max-tokens="DEFAULT_LLM_MAX_TOKENS"
          :mid-active-sections="midActiveSections"
          :on-mid-sections-change="onMidSectionsChange"
          :novels-loading="novelsLoading"
          :novels="novels"
          :current-novel-title="currentNovelTitle"
          :running="running"
          :anchors-loading="anchorsLoading"
          :anchors="anchors"
          :inferred-time-slot-hint="inferredTimeSlotHint"
          :all-character-options="allCharacterOptions"
          :previewing-input="previewingInput"
          :open-create-dialog="openCreateDialog"
          :on-pov-change="onPovChange"
          :on-focus-change="onFocusChange"
          :open-role-manager="openRoleManager"
          :run-generate="runGenerate"
          :run-expand="runExpand"
          :run-optimize="runOptimize"
          :run-init-world="runInitWorld"
          :abort-run="abortRun"
        />
      </div>

      <div class="resize-handle" @mousedown="startResizeMid" title="拖动调整中间栏宽度"></div>

      <div class="right-pane">
        <RightPanel
          :running="running"
          :run-phase="runPhase"
          :run-phase-label="runPhaseLabel"
          :run-hint="runHint"
          :token-usage-text="tokenUsageText"
          :last-output-path="lastOutputPath"
          :right-tab="rightTab"
          :graph-view="graph.graphView"
          :graph-view-label="graph.graphViewLabel"
          :open-graph-dialog="graph.openGraphDialog"
          :on-right-tab-change="onRightTabChange"
          :result-text="resultText"
          :next-status-text="nextStatusText"
          :plan-stream-text="planStreamText"
          :novel-id="form.novelId"
        />
      </div>
    </div>
  </div>

  <TextPreviewDialog v-model="dialogVisible" :title="dialogTitle" :text="dialogText" />

  <CreateNovelDialog
    v-model="createDialogVisible"
    v-model:novel-title="createForm.novelTitle"
    v-model:start-time-slot="createForm.startTimeSlot"
    v-model:pov-character-id="createForm.povCharacterId"
    :running="running"
    @create="createNovel"
  />

  <InputPreviewDialog
    v-model="inputPreviewVisible"
    v-model:open-stages="inputPreviewOpenStages"
    :input-preview-data="inputPreviewData"
    :running="running"
    :pending-run-starting="pendingRunStarting"
    :pending-run-payload="pendingRunPayload"
    @copy-json="copyInputPreviewJson"
    @confirm="confirmRunFromPreview"
  />

  <GraphDialogs :novel-id="form.novelId" />

  <RoleManagerDialog
    v-model="roleManagerVisible"
    v-model:character-tag-draft="characterTagDraft"
    :all-character-options="allCharacterOptions"
    @add="addCharacterTag"
    @remove="removeCharacterTag"
  />
</template>

<script lang="ts" setup>
import { computed, nextTick, onMounted, provide, reactive, ref, toRef, watch } from "vue";
import { ElMessage } from "element-plus";
import { apiJson, apiSse, logDebug } from "./api/client";
import { usePanelResize } from "./composables/usePanelResize";
import { GRAPH_INJECTION_KEY, useGraph } from "./composables/useGraph";
import TagPanel from "./components/TagPanel.vue";
import MidFormPanel from "./components/MidFormPanel.vue";
import RightPanel from "./components/RightPanel.vue";
import GraphDialogs from "./components/graph/GraphDialogs.vue";
import TextPreviewDialog from "./components/dialogs/TextPreviewDialog.vue";
import CreateNovelDialog from "./components/dialogs/CreateNovelDialog.vue";
import InputPreviewDialog from "./components/dialogs/InputPreviewDialog.vue";
import RoleManagerDialog from "./components/dialogs/RoleManagerDialog.vue";

type AppRunMode =
  | "init_state"
  | "plan_only"
  | "write_chapter"
  | "revise_chapter"
  | "expand_chapter"
  | "optimize_suggestions";

const { leftPanelWidth, midPanelWidth, startResizeLeft, startResizeMid } = usePanelResize();

const tagsLoading = ref(true);
const tags = ref<string[]>([]);
const tagGroups = ref<Record<string, string[]>>({});
const selectedTags = ref<string[]>([]);
const tagTreeRef = ref<{ setCheckedKeys: (k: unknown[], leafOnly?: boolean) => void; getCheckedKeys: (leafOnly?: boolean) => unknown[]; getHalfCheckedKeys: () => unknown[] } | null>(null);
function onTagTreeRef(el: unknown) {
  tagTreeRef.value = el as typeof tagTreeRef.value;
}
const novelsLoading = ref(true);
const novels = ref<Array<{ novel_id: string; novel_title: string }>>([]);
const previewCache = reactive<Record<string, string>>({});
const previewFullCache = reactive<Record<string, string>>({});

const anchorsLoading = ref(false);
const anchors = ref<Array<{ id: string; label: string; type: string; time_slot: string }>>([]);
const characterOptions = ref<string[]>([]);
const customCharacterOptions = ref<string[]>([]);
const hiddenCharacterOptions = ref<string[]>([]);
const characterTagDraft = ref("");
const buildingLoreSummary = ref(false);

const running = ref(false);
let runAbortController: AbortController | null = null;
const resultText = ref("等待你的操作...");
const nextStatusText = ref("");
const planStreamText = ref("");
const runPhase = ref<
  "idle" | "planning" | "writing" | "optimizing" | "saving" | "outputs_written" | "done" | "error"
>("idle");
const runHint = ref("");
const lastOutputPath = ref("");
const tokenUsageText = ref("");

const rightTab = ref<"result" | "next" | "plan" | "graph">("result");
function onRightTabChange(v: "result" | "next" | "plan" | "graph") {
  rightTab.value = v;
}

const dialogVisible = ref(false);
const dialogTitle = ref("");
const dialogText = ref("");
const roleManagerVisible = ref(false);
const midActiveSections = ref<Array<string>>(["basic", "timeline", "task"]);
function onMidSectionsChange(v: string[]) {
  midActiveSections.value = Array.isArray(v) ? v : [];
}
function openRoleManager() {
  roleManagerVisible.value = true;
}

const createDialogVisible = ref(false);
const previewingInput = ref(false);
const inputPreviewVisible = ref(false);
const inputPreviewData = ref<Record<string, unknown> | null>(null);
const inputPreviewOpenStages = ref<string[]>([]);

function setInputPreviewFromApi(data: unknown) {
  inputPreviewData.value = data && typeof data === "object" ? (data as Record<string, unknown>) : null;
  const stages = inputPreviewData.value?.stages;
  const n = Array.isArray(stages) ? stages.length : 0;
  inputPreviewOpenStages.value = n ? Array.from({ length: n }, (_, i) => String(i)) : [];
}

async function copyInputPreviewJson() {
  if (!inputPreviewData.value) return;
  const text = JSON.stringify(inputPreviewData.value, null, 2);
  try {
    await navigator.clipboard.writeText(text);
    ElMessage.success("已复制到剪贴板");
  } catch {
    ElMessage.error("复制失败，请手动选择文本或检查浏览器权限");
  }
}
const pendingRunPayload = ref<unknown>(null);
const pendingRunNovelId = ref("");
const pendingRunStarting = ref(false);

const createForm = reactive<{
  novelTitle: string;
  startTimeSlot: string;
  povCharacterId: string;
}>({
  novelTitle: "",
  startTimeSlot: "",
  povCharacterId: "",
});

function openCreateDialog() {
  createDialogVisible.value = true;
}

/** 与 agents/novel/llm_client.init_deepseek_chat 默认参数保持一致（勿与后端漂移） */
const DEFAULT_LLM_TEMPERATURE = 0.7;
const DEFAULT_LLM_MAX_TOKENS = 20000;

const form = reactive<{
  novelId: string;
  eventMode: "existing" | "new";
  existingEventId: string;
  newEventTimeSlot: string;
  newEventSummary: string;
  newEventPrevId: string;
  newEventNextId: string;
  povCharacterOverride: string[];
  focusCharacterIds: string[];
  chapterPresetName: string;
  userTask: string;
  llmTemperature: number | null;
  llmTopP: number | null;
  llmMaxTokens: number | null;
}>({
  novelId: "",
  eventMode: "existing",
  existingEventId: "",
  newEventTimeSlot: "",
  newEventSummary: "",
  newEventPrevId: "",
  newEventNextId: "",
  povCharacterOverride: [],
  focusCharacterIds: [],
  chapterPresetName: "",
  userTask: "",
  llmTemperature: DEFAULT_LLM_TEMPERATURE,
  llmTopP: null,
  llmMaxTokens: DEFAULT_LLM_MAX_TOKENS,
});

const graph = useGraph(toRef(form, "novelId"));
provide(GRAPH_INJECTION_KEY, graph);

const inferredTimeSlotHint = computed(() => {
  const byId = new Map((anchors.value || []).map((a) => [a.id, a]));
  if (form.eventMode === "existing") {
    const slot = form.existingEventId ? byId.get(form.existingEventId)?.time_slot : "";
    return slot || "";
  }
  const slot = (form.newEventTimeSlot || "").trim();
  if (slot) return slot;
  const after = form.newEventPrevId ? byId.get(form.newEventPrevId)?.time_slot : "";
  const before = form.newEventNextId ? byId.get(form.newEventNextId)?.time_slot : "";
  if (after && before) return `${after}之后~${before}之前`;
  if (after) return `${after}之后`;
  if (before) return `${before}之前`;
  return "";
});

const currentNovelTitle = computed(() => {
  const id = (form.novelId || "").trim();
  if (!id) return "";
  const hit = novels.value.find((n) => n.novel_id === id);
  return hit?.novel_title || "";
});

const allCharacterOptions = computed(() => {
  const hidden = new Set(hiddenCharacterOptions.value || []);
  const merged = [...(characterOptions.value || []), ...(customCharacterOptions.value || [])]
    .map((x) => String(x || "").trim())
    .filter((x) => !!x && !hidden.has(x));
  return Array.from(new Set(merged));
});

const runPhaseLabel = computed(() => {
  const p = runPhase.value;
  if (p === "idle") return "待命";
  if (p === "planning") return "正在规划章节";
  if (p === "writing") return "正在生成正文";
  if (p === "optimizing") return "正在生成优化建议";
  if (p === "saving") return "正在保存章节、状态与三表";
  if (p === "outputs_written") return "正文已写入 outputs";
  if (p === "done") return "已完成";
  if (p === "error") return "执行失败";
  return p;
});

type TagTreeNode = { id: string; label: string; children?: TagTreeNode[]; isLeaf?: boolean; tag?: string };
const tagTreeData = computed<TagTreeNode[]>(() => {
  const roots: TagTreeNode[] = [];
  const byId = new Map<string, TagTreeNode>();
  for (const tag of tags.value) {
    const parts = tag.split("/").filter(Boolean);
    if (parts.length === 0) continue;
    let parentId = "";
    let parentChildren = roots;
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const id = parentId ? `${parentId}/${part}` : part;
      let node = byId.get(id);
      if (!node) {
        node = { id, label: part, children: [] };
        byId.set(id, node);
        parentChildren.push(node);
      }
      if (i === parts.length - 1) {
        node.isLeaf = true;
        node.tag = tag;
      }
      parentId = id;
      parentChildren = node.children || (node.children = []);
    }
  }
  return roots;
});

function abortRun() {
  if (!running.value) return;
  try {
    runAbortController?.abort();
  } catch {
    // ignore
  }
}

function selectAll() {
  selectedTags.value = [...tags.value];
  nextTick(() => {
    if (tagTreeRef.value) tagTreeRef.value.setCheckedKeys([...tags.value], false);
  });
}
function clearSelect() {
  selectedTags.value = [];
  nextTick(() => {
    if (tagTreeRef.value) tagTreeRef.value.setCheckedKeys([], false);
  });
}
function invertSelect() {
  const set = new Set(selectedTags.value);
  selectedTags.value = tags.value.filter((t) => !set.has(t));
  nextTick(() => {
    if (tagTreeRef.value) tagTreeRef.value.setCheckedKeys([...selectedTags.value], false);
  });
}
function onTreeCheck() {
  if (!tagTreeRef.value) return;
  const checkedKeys: string[] = tagTreeRef.value.getCheckedKeys(false) || [];
  const halfKeys: string[] = tagTreeRef.value.getHalfCheckedKeys() || [];
  const all = [...checkedKeys, ...halfKeys];
  selectedTags.value = all.filter((k) => tags.value.includes(k));
}

async function loadTags() {
  tagsLoading.value = true;
  const res = (await apiJson("/api/lore/tags", "GET", null)) as { tags?: string[]; groups?: Record<string, string[]> };
  tags.value = res.tags || [];
  tagGroups.value = res.groups || {};
  selectedTags.value = [...tags.value];
  for (const k of Object.keys(previewCache)) delete previewCache[k];
  for (const k of Object.keys(previewFullCache)) delete previewFullCache[k];
  tagsLoading.value = false;
  logDebug(`Loaded tags count=${tags.value.length}`);
  await nextTick();
  if (tagTreeRef.value) tagTreeRef.value.setCheckedKeys([...selectedTags.value], false);
}

async function buildCurrentLoreSummary() {
  const tagsNow = selectedTags.value || [];
  if (tagsNow.length === 0) {
    ElMessage.error("请至少勾选 1 个设定标签。");
    return;
  }
  buildingLoreSummary.value = true;
  try {
    const res = (await apiJson("/api/lore/summary/build", "POST", { tags: tagsNow, force: true })) as {
      tag_summaries?: unknown[];
      summary_text?: string;
    };
    const rows = Array.isArray(res?.tag_summaries) ? res.tag_summaries : [];
    const text = rows.length
      ? rows
          .map((x: unknown) => {
            const o = x as { tag?: string; summary?: string };
            return `【${String(o?.tag || "")}】\n${String(o?.summary || "")}`;
          })
          .join("\n\n")
      : String(res?.summary_text || "");
    dialogTitle.value = "Tag摘要预览";
    dialogText.value = text;
    dialogVisible.value = true;
    ElMessage.success("已按当前勾选标签重新生成摘要");
  } finally {
    buildingLoreSummary.value = false;
  }
}

async function loadNovels() {
  novelsLoading.value = true;
  try {
    const res = (await apiJson("/api/novels", "GET", null)) as { novels?: Array<{ novel_id: string; novel_title: string }> };
    novels.value = res.novels || [];

    if (!form.novelId && novels.value.length > 0) {
      form.novelId = novels.value[0].novel_id;
    }
  } finally {
    novelsLoading.value = false;
  }
}

async function loadAnchors() {
  const novelId = (form.novelId || "").trim();
  anchors.value = [];
  form.existingEventId = "";
  form.newEventTimeSlot = "";
  form.newEventSummary = "";
  form.newEventPrevId = "";
  form.newEventNextId = "";
  form.eventMode = "existing";
  if (!novelId) return;
  anchorsLoading.value = true;
  try {
    const res = (await apiJson(`/api/novels/${encodeURIComponent(novelId)}/anchors`, "GET", null)) as {
      anchors?: Array<{ id: string; label: string; type: string; time_slot: string }>;
    };
    anchors.value = res.anchors || [];
  } catch (e: unknown) {
    const err = e as { message?: string };
    logDebug("loadAnchors failed: " + (err?.message || String(e)));
  } finally {
    anchorsLoading.value = false;
  }
}

async function loadCharacterOptions() {
  const novelId = (form.novelId || "").trim();
  characterOptions.value = [];
  hiddenCharacterOptions.value = [];
  customCharacterOptions.value = [];
  characterTagDraft.value = "";
  form.povCharacterOverride = [];
  form.focusCharacterIds = [];
  if (!novelId) return;
  try {
    const res = (await apiJson(
      `/api/novels/${encodeURIComponent(novelId)}/character_entities`,
      "GET",
      null
    )) as { character_ids?: string[] };
    const ids = Array.isArray(res?.character_ids) ? res.character_ids : [];
    characterOptions.value = Array.from(new Set(ids.map((x) => String(x || "").trim()).filter(Boolean)));
  } catch (e: unknown) {
    const err = e as { message?: string };
    logDebug("loadCharacterOptions failed: " + (err?.message || String(e)));
  }
}

function addCharacterTag() {
  const v = String(characterTagDraft.value || "").trim();
  if (!v) return;
  if (!customCharacterOptions.value.includes(v) && !characterOptions.value.includes(v)) {
    customCharacterOptions.value.push(v);
  }
  hiddenCharacterOptions.value = hiddenCharacterOptions.value.filter((x) => x !== v);
  characterTagDraft.value = "";
}

function removeCharacterTag(cid: string) {
  const key = String(cid || "").trim();
  if (!key) return;
  if (!hiddenCharacterOptions.value.includes(key)) hiddenCharacterOptions.value.push(key);
  customCharacterOptions.value = customCharacterOptions.value.filter((x) => x !== key);
  form.povCharacterOverride = (form.povCharacterOverride || []).filter((x) => x !== key);
  form.focusCharacterIds = (form.focusCharacterIds || []).filter((x) => x !== key);
}

function onPovChange(v: unknown) {
  const arr = Array.isArray(v) ? v : [];
  for (const item of arr) {
    const key = String(item || "").trim();
    if (!key) continue;
    if (!allCharacterOptions.value.includes(key)) customCharacterOptions.value.push(key);
    hiddenCharacterOptions.value = hiddenCharacterOptions.value.filter((x) => x !== key);
  }
}

function onFocusChange(v: unknown) {
  const arr = Array.isArray(v) ? v : [];
  for (const item of arr) {
    const key = String(item || "").trim();
    if (!key) continue;
    if (!allCharacterOptions.value.includes(key)) customCharacterOptions.value.push(key);
    hiddenCharacterOptions.value = hiddenCharacterOptions.value.filter((x) => x !== key);
  }
}

async function loadPreview(tag: string) {
  if (Object.prototype.hasOwnProperty.call(previewCache, tag)) return;
  const url = `/api/lore/preview?tag=${encodeURIComponent(tag)}&max_chars=0&compact=1`;
  const res = (await apiJson(url, "GET", null)) as { preview?: string };
  previewCache[tag] = res && res.preview ? res.preview : "";
  logDebug(`Loaded preview tag=${tag} len=${previewCache[tag].length}`);
}

async function loadPreviewFull(tag: string) {
  if (Object.prototype.hasOwnProperty.call(previewFullCache, tag)) return;
  const url = `/api/lore/preview?tag=${encodeURIComponent(tag)}&max_chars=0&compact=0`;
  const res = (await apiJson(url, "GET", null)) as { preview?: string };
  previewFullCache[tag] = res && res.preview ? res.preview : "";
}

async function preloadAllPreviews() {
  const list = tags.value || [];
  if (list.length === 0) return;
  await Promise.all(list.map((t) => loadPreview(t).catch(() => {})));
}

function getTagPreview(tag: string) {
  if (Object.prototype.hasOwnProperty.call(previewCache, tag)) return previewCache[tag];
  return "预览尚未加载（请稍等）";
}

async function openTagDialog(tag: string) {
  dialogTitle.value = "设定预览： " + tag;
  logDebug(`openTagDialog tag=${tag}`);
  if (Object.prototype.hasOwnProperty.call(previewFullCache, tag)) {
    dialogText.value = previewFullCache[tag];
  } else {
    dialogText.value = "预览加载中...";
    await loadPreviewFull(tag).catch(() => {});
    dialogText.value = previewFullCache[tag] || "";
  }
  dialogVisible.value = true;
}

async function createNovel() {
  resultText.value = "创建中...";
  const payload = {
    novel_title: (createForm.novelTitle || "").trim() || "未命名小说",
    start_time_slot: (createForm.startTimeSlot || "").trim() || null,
    pov_character_id: (createForm.povCharacterId || "").trim() || null,
    initial_user_task: null,
    lore_tags: selectedTags.value,
  };
  const res = (await apiJson("/api/novels", "POST", payload)) as { novel_id: string };
  form.novelId = res.novel_id;
  createForm.novelTitle = "";
  createForm.startTimeSlot = "";
  createForm.povCharacterId = "";
  await loadNovels();
  await loadAnchors();
  resultText.value = `创建成功！\n\n若尚未初始化世界，请展开「高级」点击「初始化世界」；否则可直接使用下方三个写作按钮。`;
  createDialogVisible.value = false;
}

function buildRunPayload(runMode: AppRunMode) {
  const novelId = (form.novelId || "").trim();
  if (!novelId) {
    ElMessage.error("请先创建新小说或填写小说编号。");
    return null;
  }

  const loreTags = selectedTags.value || [];
  if (loreTags.length === 0) {
    ElMessage.error("请至少勾选 1 项设定（lores 下对应标签）。");
    return null;
  }
  if (!form.userTask || !form.userTask.trim()) {
    ElMessage.error("请填写任务框内容（生成/扩写/优化/初始化均需要）。");
    return null;
  }
  if (runMode !== "optimize_suggestions" && runMode !== "init_state") {
    if (!validateTimePlan()) {
      return null;
    }
  }

  const mergedTask = (() => {
    const base = form.userTask || "";
    const picked = (form.focusCharacterIds || []).filter(Boolean);
    if (picked.length === 0) return base;
    return `${base}\n\n（配角设定：${picked.join("、")}）`;
  })();
  const payload: Record<string, unknown> = {
    mode: runMode,
    user_task: mergedTask,
    existing_event_id: form.eventMode === "existing" ? (form.existingEventId || null) : null,
    new_event_time_slot: form.eventMode === "new" ? (form.newEventTimeSlot || null) : null,
    new_event_summary: form.eventMode === "new" ? (form.newEventSummary || null) : null,
    new_event_prev_id: form.eventMode === "new" ? (form.newEventPrevId || null) : null,
    new_event_next_id: form.eventMode === "new" ? (form.newEventNextId || null) : null,
    time_slot_override: null,
    pov_character_ids_override: (form.povCharacterOverride || []).filter(Boolean),
    supporting_character_ids: (form.focusCharacterIds || []).filter(Boolean),
    chapter_preset_name: form.chapterPresetName || null,
    lore_tags: loreTags,
  };
  payload.llm_temperature =
    form.llmTemperature != null && !Number.isNaN(form.llmTemperature)
      ? form.llmTemperature
      : DEFAULT_LLM_TEMPERATURE;
  payload.llm_max_tokens = Math.round(
    form.llmMaxTokens != null && !Number.isNaN(form.llmMaxTokens)
      ? form.llmMaxTokens
      : DEFAULT_LLM_MAX_TOKENS
  );
  if (form.llmTopP != null && !Number.isNaN(form.llmTopP)) {
    payload.llm_top_p = form.llmTopP;
  }
  return { novelId, payload };
}

async function executeRun(novelId: string, payload: Record<string, unknown>) {
  running.value = true;
  runAbortController = new AbortController();
  runPhase.value = "planning";
  runHint.value = "已提交任务，正在排队/规划...";
  lastOutputPath.value = "";
  tokenUsageText.value = "";
  nextStatusText.value = "";
  planStreamText.value = "";
  try {
    const startAt = Date.now();
    let logText = "（流式输出开始）\n";
    let accContent = "";
    let donePayload: Record<string, unknown> | null = null;
    const refreshStreamText = () => {
      resultText.value = `${logText}\n\n[content]\n${accContent}`;
    };

    await apiSse(`/api/novels/${novelId}/run_stream`, "POST", payload, (evt) => {
      const d = evt.data as Record<string, unknown> | null | undefined;
      if (evt.event === "phase") {
        const name = String(d?.name || "running");
        if (name === "planning" || name === "writing" || name === "saving" || name === "outputs_written") {
          runPhase.value = name;
        }
        if (name === "planning") rightTab.value = "plan";
        if (name === "writing" || name === "optimizing") rightTab.value = "result";
        if (name === "next_status") rightTab.value = "next";
        const extra = name === "writing" && d?.chapter_index ? ` chapter=${d.chapter_index}` : "";
        const out = name === "outputs_written" && d?.path ? ` path=${d.path}` : "";
        if (name === "planning") runHint.value = "正在生成章节规划（beats + next_state）";
        if (name === "writing") runHint.value = "正在流式生成正文，请稍候...";
        if (name === "optimizing") runHint.value = "正在流式生成优化建议...";
        if (name === "saving") runHint.value = "正在保存章节记录、世界状态和图谱三表";
        if (name === "next_status") runHint.value = "正在生成下章建议...";
        if (name === "next_status_done") runHint.value = "下章建议已生成";
        if (name === "next_status_failed") runHint.value = "下章建议生成失败（可重试）";
        if (name === "outputs_written") {
          lastOutputPath.value = String(d?.path || "");
          runHint.value = "正文已归档到 outputs，可在本地打开查看";
        }
        if (name === "next_status_failed") {
          const msg = String(d?.error || "未知错误");
          nextStatusText.value = `（下章建议生成失败）${msg}`;
          rightTab.value = "next";
        }
        logText += `\n[phase] ${name}${extra}${out}\n`;
        refreshStreamText();
      } else if (evt.event === "plan_content") {
        const delta = d?.delta || "";
        rightTab.value = "plan";
        planStreamText.value += String(delta);
      } else if (evt.event === "content") {
        const delta = d?.delta || "";
        rightTab.value = "result";
        accContent += String(delta);
        refreshStreamText();
      } else if (evt.event === "error") {
        const msg = d?.message || JSON.stringify(d);
        runPhase.value = "error";
        runHint.value = "执行失败，请查看下方错误日志";
        logText += `\n[error]\n${msg}\n`;
        refreshStreamText();
      } else if (evt.event === "done") {
        donePayload = (d || null) as Record<string, unknown> | null;
        runPhase.value = "done";
        runHint.value = "本次任务已完成";
      }
    }, runAbortController.signal);

    if (donePayload) {
      const ms = Date.now() - startAt;
      const ch = donePayload.chapter_index ? `chapter_index=${donePayload.chapter_index}` : "chapter_index=(auto)";
      const st = donePayload.state_updated ? "state_updated=true" : "state_updated=false";
      const u = (donePayload.usage_metadata || {}) as Record<string, unknown>;
      const input = u.input_tokens ?? u.prompt_tokens ?? u.input_token_count ?? null;
      const output = u.output_tokens ?? u.completion_tokens ?? u.output_token_count ?? null;
      const total =
        u.total_tokens ??
        u.total_token_count ??
        (typeof input === "number" && typeof output === "number" ? input + output : null);
      if (input !== null || output !== null || total !== null) {
        tokenUsageText.value = `input=${input ?? "-"}, output=${output ?? "-"}, total=${total ?? "-"}`;
      }
      logText += `\n[done] ${ch}, ${st}, elapsed_ms=${ms}\n`;
      nextStatusText.value = String(donePayload.next_status || "").trim();
      if (nextStatusText.value) {
        rightTab.value = "next";
      }
      refreshStreamText();
    }
    await loadAnchors();
    if (graph.graphFullscreenVisible || rightTab.value === "graph") {
      await graph.loadGraph();
    }
  } catch (e: unknown) {
    const err = e as { name?: string; message?: string };
    const aborted = err?.name === "AbortError";
    if (aborted) {
      runPhase.value = "idle";
      runHint.value = "已手动中止本次生成";
      resultText.value += "\n\n[abort]\n用户已手动中止本次流式生成。\n";
    } else {
      runPhase.value = "error";
      runHint.value = "执行失败，请查看错误信息";
      ElMessage.error(`运行失败：${err?.message || String(e)}`);
    }
  } finally {
    running.value = false;
    runAbortController = null;
  }
}

async function startPreviewRun(runMode: AppRunMode) {
  const built = buildRunPayload(runMode);
  if (!built) return;
  previewingInput.value = true;
  runPhase.value = "idle";
  runHint.value = "正在生成本次 Input 预览...";
  try {
    const data = await apiJson(
      `/api/novels/${encodeURIComponent(built.novelId)}/preview_input`,
      "POST",
      built.payload
    );
    setInputPreviewFromApi(data);
    pendingRunPayload.value = built.payload;
    pendingRunNovelId.value = built.novelId;
    runHint.value = "Input 已生成，请在弹窗点击“确认并运行”";
    inputPreviewVisible.value = true;
  } finally {
    previewingInput.value = false;
  }
}

function runGenerate() {
  return startPreviewRun("write_chapter");
}
function runExpand() {
  return startPreviewRun("expand_chapter");
}
function runOptimize() {
  return startPreviewRun("optimize_suggestions");
}
function runInitWorld() {
  return startPreviewRun("init_state");
}

async function confirmRunFromPreview() {
  if (!pendingRunPayload.value || !pendingRunNovelId.value) {
    ElMessage.error("没有可运行的预览内容，请先点击主按钮生成 Input。");
    return;
  }
  pendingRunStarting.value = true;
  runHint.value = "已确认，准备开始运行...";
  inputPreviewVisible.value = false;
  try {
    await executeRun(
      pendingRunNovelId.value,
      pendingRunPayload.value as Record<string, unknown>
    );
  } finally {
    pendingRunStarting.value = false;
  }
}

function validateTimePlan(): boolean {
  if (form.eventMode === "existing") {
    if (!(form.existingEventId || "").trim()) {
      ElMessage.error("请先选择“归属到已有事件”。");
      return false;
    }
    return true;
  }
  if (!(form.newEventTimeSlot || "").trim() || !(form.newEventSummary || "").trim()) {
    ElMessage.error("新建事件时请填写 time_slot 和 summary。");
    return false;
  }
  if (
    (form.newEventPrevId || "").trim() &&
    (form.newEventNextId || "").trim() &&
    form.newEventPrevId === form.newEventNextId
  ) {
    ElMessage.error("新建事件的前后事件不能相同。");
    return false;
  }
  return true;
}

onMounted(async () => {
  try {
    await loadTags();
    await loadNovels();
    await loadAnchors();
    await loadCharacterOptions();
    await preloadAllPreviews();
  } catch (e: unknown) {
    const err = e as { message?: string };
    tagsLoading.value = false;
    logDebug("loadTags/preload failed: " + (err?.message || String(e)));
  }
});

watch(
  () => form.novelId,
  async () => {
    await loadAnchors();
    await loadCharacterOptions();
  }
);
</script>

<style scoped>
.wrap {
  max-width: 1400px;
  margin: 0 auto;
}
.header {
  margin-top: 0;
  margin-bottom: 14px;
}
.main-layout {
  display: flex;
  gap: 12px;
  align-items: stretch;
}
.left-pane {
  flex: 0 0 auto;
  min-width: 280px;
}
.mid-pane {
  flex: 0 0 auto;
  min-width: 360px;
}
.right-pane {
  flex: 1 1 auto;
  min-width: 420px;
}
.resize-handle {
  width: 10px;
  cursor: col-resize;
  border-radius: 6px;
  background: linear-gradient(
    to right,
    transparent 0%,
    transparent 38%,
    #cbd5e1 38%,
    #94a3b8 50%,
    #cbd5e1 62%,
    transparent 62%,
    transparent 100%
  );
  transition:
    filter 0.2s,
    background-color 0.2s;
  position: relative;
  z-index: 10;
  flex: 0 0 10px;
}
.resize-handle:hover {
  filter: brightness(0.9);
}
.muted {
  color: #909399;
  font-size: 12px;
}
.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.tag-list-scroll {
  max-height: 72vh;
  overflow: auto;
  padding-right: 6px;
}
.tag-item {
  display: inline-flex;
}
.tag-tree {
  font-size: 13px;
}
.tree-node-row {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.tree-node-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tag-hint {
  margin-top: 6px;
  font-size: 12px;
  color: #909399;
}
.preview-scroll {
  max-height: 420px;
  overflow: auto;
  padding: 6px 2px;
}
.tag-preview {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
}
.tag-popover :deep(.el-popper__content) {
  max-height: 420px;
  overflow: auto;
}
.choice-cards {
  width: 100%;
}
.choice-cards :deep(.el-radio-button__inner) {
  width: 100%;
}
</style>
