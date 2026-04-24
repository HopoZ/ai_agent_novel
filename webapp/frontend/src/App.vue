<template>
  <div class="app-literary">
    <div class="wrap">
      <header class="app-header">
        <div class="app-header-text">
          <div class="app-header-top">
            <el-button text type="primary" size="small" @click="openLoresDir">打开输入</el-button>
            <div class="app-header-titles">
              <p class="app-tagline">规划 · 写作 · 图谱</p>
              <h1 class="app-title">AI 小说创作代理</h1>
            </div>
            <div class="app-header-actions">
              <el-button text type="primary" size="small" @click="openOutputsDir">打开输出</el-button>
              <el-button type="primary" plain size="small" @click="apiSettingsVisible = true">
                API 密钥
              </el-button>
            </div>
          </div>
        </div>
        <div class="app-header-accent" aria-hidden="true"></div>
      </header>

      <el-alert
        v-if="firstRunHintVisible"
        class="first-run-alert"
        type="info"
        show-icon
        closable
        title="首次使用请先完成"
        @close="dismissFirstRun"
      >
        <ol class="first-run-list">
          <li>点击右上角「API 密钥」，按提供商填写并保存（DeepSeek 或 OpenAI 兼容）。</li>
          <li>点击左侧「打开输入」，在 <strong>lores</strong> 文件夹内按子目录放入 <strong>.md</strong> 设定（路径即标签）；保存后左侧勾选标签。</li>
          <li>写作生成的正文在「打开输出」对应目录。</li>
        </ol>
        <p class="first-run-muted">桌面安装版可一键打开输入与输出文件夹。</p>
      </el-alert>

      <div class="main-layout" :class="{ 'main-layout--stack': layoutStacked }">
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
          :mid-active-section="midActiveSection"
          :on-mid-section-change="onMidSectionChange"
          :novels-loading="novelsLoading"
          :novels="novels"
          :current-novel-title="currentNovelTitle"
          :running="running"
          :anchors-loading="anchorsLoading"
          :anchors="anchors"
          :inferred-time-slot-hint="inferredTimeSlotHint"
          :suggested-timeline-event-label="suggestedTimelineEventLabel"
          :all-character-options="allCharacterSelectOptions"
          :previewing-input="previewingInput"
          :open-create-dialog="openCreateDialog"
          :on-pov-change="onPovChange"
          :on-focus-change="onFocusChange"
          :apply-suggested-timeline-event="applySuggestedTimelineEvent"
          :open-role-manager="openRoleManager"
          :run-generate="runGenerate"
          :run-expand="runExpand"
          :run-init-world="runInitWorld"
          :run-optimize="runOptimize"
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
          :shadow-digest-text="shadowDigestText"
          :consistency-audit-text="consistencyAuditText"
          :consistency-audit-severity="consistencyAuditSeverity"
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
    :structure-gate="previewStructureGate"
    @copy-json="copyInputPreviewJson"
    @confirm="confirmRunFromPreview"
    @confirm-risk="confirmRunFromPreviewRisk"
  />

  <GraphDialogs :novel-id="form.novelId" />

  <RoleManagerDialog
    v-model="roleManagerVisible"
    v-model:character-tag-draft="characterTagDraft"
    :all-character-options="allCharacterSelectOptions"
    @add="addCharacterTag"
    @remove="removeCharacterTag"
  />

  <NextChapterHintDialog
    v-model="nextChapterHintVisible"
    v-model:draft="nextChapterHintDraft"
    :previewing-input="previewingInput"
    @confirm="confirmNextChapterFromHint"
  />

  <OptimizeIntentDialog
    v-model="optimizeIntentVisible"
    v-model:direction-draft="optimizeIntentDraft"
    :previewing-input="previewingInput"
    @confirm="confirmOptimizeIntent"
  />

  <ApiSettingsDialog v-model="apiSettingsVisible" />

  <WorldInitDialog
    v-model="worldInitDialogVisible"
    :running="running && currentStreamMode === 'init_state'"
    :phase-label="runPhaseLabel"
    :hint="runHint"
    :stream-text="worldInitStreamText"
    :token-usage="tokenUsageText"
    :error-message="worldInitError"
    @abort="abortRun"
  />
</template>

<script lang="ts" setup>
import { computed, nextTick, onMounted, provide, reactive, ref, toRef, watch } from "vue";
import { ElMessage } from "element-plus";
import { apiJson, apiSse, logDebug } from "./api/client";
import { getNovelAgentDesktop } from "./desktop";
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
import NextChapterHintDialog from "./components/dialogs/NextChapterHintDialog.vue";
import OptimizeIntentDialog from "./components/dialogs/OptimizeIntentDialog.vue";
import ApiSettingsDialog from "./components/dialogs/ApiSettingsDialog.vue";
import WorldInitDialog from "./components/dialogs/WorldInitDialog.vue";

type AppRunMode =
  | "init_state"
  | "plan_only"
  | "write_chapter"
  | "revise_chapter"
  | "expand_chapter"
  | "optimize_suggestions";

/** 新建小说引导弹窗里「用模型初始化」的默认任务句（可覆盖） */
const DEFAULT_INIT_STATE_USER_TASK =
  "根据左侧已勾选的设定，生成完整 NovelState（世界观、人物、连续性）；尊重本小说创建时填写的起始时间段与视角。";

const { leftPanelWidth, midPanelWidth, layoutStacked, startResizeLeft, startResizeMid } =
  usePanelResize();

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
/** 来自后端的角色候选项：value 为稳定 id，label 为展示名（中文名等） */
const characterOptionRows = ref<Array<{ id: string; label: string }>>([]);
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
  | "idle"
  | "world_init"
  | "planning"
  | "writing"
  | "optimizing"
  | "saving"
  | "outputs_written"
  | "done"
  | "error"
>("idle");
const runHint = ref("");
const lastOutputPath = ref("");
const tokenUsageText = ref("");
const shadowDigestText = ref("");
const consistencyAuditText = ref("");
const consistencyAuditSeverity = ref<"ok" | "warn" | "high">("ok");

/** 当前 run_stream 的 mode（用于独立初始化窗口的 running 态等） */
const currentStreamMode = ref("");
const worldInitDialogVisible = ref(false);
const worldInitStreamText = ref("");
const worldInitError = ref("");

const rightTab = ref<"result" | "next" | "plan" | "graph">("result");
function onRightTabChange(v: "result" | "next" | "plan" | "graph") {
  rightTab.value = v;
}

const dialogVisible = ref(false);
const dialogTitle = ref("");
const dialogText = ref("");
const roleManagerVisible = ref(false);
/** 中间栏折叠：accordion 一次只展开一块（与 MidFormPanel el-collapse accordion 一致） */
const midActiveSection = ref<string>("task");
function onMidSectionChange(v: string | string[]) {
  midActiveSection.value = Array.isArray(v) ? String(v[0] ?? "") : String(v ?? "");
}
function openRoleManager() {
  roleManagerVisible.value = true;
}

const createDialogVisible = ref(false);
const previewingInput = ref(false);
const inputPreviewVisible = ref(false);
const inputPreviewData = ref<Record<string, unknown> | null>(null);
const inputPreviewOpenStages = ref<string[]>([]);
const previewStructureGate = ref<Record<string, unknown> | null>(null);

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

const nextChapterHintVisible = ref(false);
const nextChapterHintDraft = ref("");

const optimizeIntentVisible = ref(false);
const optimizeIntentDraft = ref("");
const apiSettingsVisible = ref(false);

const FIRST_RUN_KEY = "novel-agent-onboarding-dismissed-v1";
const firstRunHintVisible = ref(false);

type SettingsResponse = {
  storage_root?: string;
  lores_dir?: string;
  outputs_dir?: string;
  deepseek_api_key_configured?: boolean;
};
const settingsPaths = ref<SettingsResponse | null>(null);

async function fetchSettingsPaths() {
  try {
    const res = (await apiJson("/api/settings", "GET", null)) as SettingsResponse;
    settingsPaths.value = res;
  } catch (e: unknown) {
    logDebug("fetchSettingsPaths failed: " + String(e));
  }
}

function dismissFirstRun() {
  try {
    localStorage.setItem(FIRST_RUN_KEY, "1");
  } catch {
    /* ignore */
  }
  firstRunHintVisible.value = false;
}

async function openDirByPath(absPath: string | undefined, label: string) {
  const p = (absPath || "").trim();
  if (!p) {
    ElMessage.warning(`${label}路径未就绪，请稍后重试。`);
    return;
  }
  const desk = getNovelAgentDesktop();
  if (desk?.openPath) {
    const r = await desk.openPath(p);
    if (!r.ok) {
      ElMessage.error(r.error || "无法打开文件夹");
    }
    return;
  }
  try {
    await navigator.clipboard.writeText(p);
    ElMessage.success(`已复制路径，请手动打开：${label}`);
  } catch {
    ElMessage.info(`${label}：${p}`);
  }
}

function openLoresDir() {
  return openDirByPath(settingsPaths.value?.lores_dir, "输入（lores）");
}

function openOutputsDir() {
  return openDirByPath(settingsPaths.value?.outputs_dir, "输出（outputs）");
}
/** 优化弹窗确认后、写入本次 preview/run 的 user_task 附加段（buildRunPayload 消费后清空） */
const pendingOptimizeDirection = ref("");
/** 从「下章提示」写入任务并打开 Input 预览时，若用户关闭预览未运行，则恢复中间栏任务原文本 */
const userTaskBeforePreviewFromNextChapter = ref<string | null>(null);
/** 最近一次写章/修订/扩写完成后，本章归属的时间线事件 id（用于「下章提示 → 生成下一章」默认同属该事件） */
const lastChapterTimelineEventId = ref("");
/** preview_input 给出的“影子编导”建议挂载事件 */
const suggestedTimelineEventId = ref("");
const suggestedTimelineEventLabel = ref("");

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
  /** 当前地图/场景，可选；随请求写入 current_map 并注入模型约束 */
  currentMap: string;
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
  currentMap: "",
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

const allCharacterSelectOptions = computed(() => {
  const hidden = new Set(hiddenCharacterOptions.value || []);
  const api = (characterOptionRows.value || []).filter((x) => x.id && !hidden.has(x.id));
  const custom = (customCharacterOptions.value || [])
    .filter((id) => id && !hidden.has(id))
    .map((id) => ({ id, label: id }));
  const byId = new Map<string, { id: string; label: string }>();
  for (const x of api) byId.set(x.id, x);
  for (const x of custom) {
    if (!byId.has(x.id)) byId.set(x.id, x);
  }
  return Array.from(byId.values());
});

const runPhaseLabel = computed(() => {
  const p = runPhase.value;
  if (p === "idle") return "待命";
  if (p === "world_init") return "正在生成本书世界观";
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
  characterOptionRows.value = [];
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
    )) as {
      character_ids?: string[];
      character_labels?: string[];
      characters?: Array<{ character_id?: string; display_name?: string }>;
    };
    let rows: Array<{ id: string; label: string }> = [];
    if (Array.isArray(res?.characters) && res.characters.length) {
      rows = res.characters
        .map((r) => {
          const id = String(r.character_id || "").trim();
          const label = String(r.display_name || r.character_id || "").trim() || id;
          return { id, label };
        })
        .filter((x) => x.id);
    } else if (Array.isArray(res?.character_ids)) {
      const ids = res.character_ids;
      const labels = res.character_labels || [];
      rows = ids
        .map((id, i) => ({
          id: String(id || "").trim(),
          label: String(labels[i] ?? id ?? "").trim() || String(id || "").trim(),
        }))
        .filter((x) => x.id);
    }
    characterOptionRows.value = rows;
  } catch (e: unknown) {
    const err = e as { message?: string };
    logDebug("loadCharacterOptions failed: " + (err?.message || String(e)));
  }
}

function addCharacterTag() {
  const v = String(characterTagDraft.value || "").trim();
  if (!v) return;
  const known = new Set([
    ...characterOptionRows.value.map((x) => x.id),
    ...customCharacterOptions.value,
  ]);
  if (!known.has(v)) {
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
  const idSet = new Set(allCharacterSelectOptions.value.map((x) => x.id));
  for (const item of arr) {
    const key = String(item || "").trim();
    if (!key) continue;
    if (!idSet.has(key)) customCharacterOptions.value.push(key);
    hiddenCharacterOptions.value = hiddenCharacterOptions.value.filter((x) => x !== key);
  }
}

function onFocusChange(v: unknown) {
  const arr = Array.isArray(v) ? v : [];
  const idSet = new Set(allCharacterSelectOptions.value.map((x) => x.id));
  for (const item of arr) {
    const key = String(item || "").trim();
    if (!key) continue;
    if (!idSet.has(key)) customCharacterOptions.value.push(key);
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
  running.value = true;
  resultText.value = "创建中…";
  const startSlot = (createForm.startTimeSlot || "").trim();
  const pov = (createForm.povCharacterId || "").trim();
  const payload = {
    novel_title: (createForm.novelTitle || "").trim() || "未命名小说",
    start_time_slot: startSlot || null,
    pov_character_id: pov || null,
    initial_user_task: null,
    lore_tags: selectedTags.value,
  };
  let res: { novel_id: string };
  try {
    res = (await apiJson("/api/novels", "POST", payload)) as { novel_id: string };
  } catch (e: unknown) {
    const err = e as { message?: string };
    ElMessage.error(`创建失败：${err?.message || String(e)}`);
    running.value = false;
    return;
  }
  const createdId = res.novel_id;
  const createdTitle = payload.novel_title;
  form.novelId = createdId;
  createForm.novelTitle = "";
  createForm.startTimeSlot = "";
  createForm.povCharacterId = "";
  createDialogVisible.value = false;
  await loadNovels();
  await loadAnchors();
  resultText.value = `《${createdTitle}》正在生成本书世界观…`;
  const initPayload = buildAutoInitStatePayload(createdTitle, startSlot, pov);
  await executeRun(createdId, initPayload);
}

/** 新建小说后自动 init_state：不经预览，直接跑 run_stream */
function buildAutoInitStatePayload(
  novelTitle: string,
  startTimeSlot: string,
  povCharacterId: string
): Record<string, unknown> {
  let userTask = DEFAULT_INIT_STATE_USER_TASK;
  const extras: string[] = [];
  if (novelTitle) extras.push(`书名：${novelTitle}`);
  if (startTimeSlot) extras.push(`起始时间段：${startTimeSlot}`);
  if (povCharacterId) extras.push(`起始视角角色：${povCharacterId}`);
  if (extras.length) userTask = `${userTask}\n\n${extras.join("\n")}`;

  const loreTags = selectedTags.value || [];
  const payload: Record<string, unknown> = {
    mode: "init_state",
    user_task: userTask,
    existing_event_id: null,
    new_event_time_slot: null,
    new_event_summary: null,
    new_event_prev_id: null,
    new_event_next_id: null,
    time_slot_override: null,
    pov_character_ids_override: povCharacterId ? [povCharacterId] : [],
    supporting_character_ids: [],
    chapter_preset_name: null,
    current_map: null,
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
  return payload;
}

function buildRunPayload(runMode: AppRunMode) {
  const novelId = (form.novelId || "").trim();
  if (!novelId) {
    ElMessage.error("请先创建新小说或填写小说编号。");
    return null;
  }

  // 影子编导无感托底：未选已有事件时，自动采用推荐事件，减少手动操作成本。
  if (
    runMode !== "optimize_suggestions" &&
    runMode !== "init_state" &&
    form.eventMode === "existing" &&
    !(form.existingEventId || "").trim()
  ) {
    const suggested = (suggestedTimelineEventId.value || "").trim();
    if (suggested.startsWith("ev:timeline:")) {
      form.existingEventId = suggested;
      ElMessage.success("已自动采用影子编导推荐事件。");
    }
  }

  const loreTags = selectedTags.value || [];
  if (loreTags.length === 0 && runMode !== "optimize_suggestions") {
    ElMessage.error("请至少勾选 1 项设定（lores 下对应标签）。");
    return null;
  }
  if (!form.userTask || !form.userTask.trim()) {
    ElMessage.error(
      runMode === "optimize_suggestions"
        ? "请先在「本章任务」中填写待优化的正文或说明。"
        : "请填写任务框内容（生成/扩写/优化/初始化均需要）。"
    );
    return null;
  }
  if (runMode !== "optimize_suggestions" && runMode !== "init_state") {
    if (!validateTimePlan()) {
      return null;
    }
  }

  let mergedTask = (() => {
    const base = form.userTask || "";
    const picked = (form.focusCharacterIds || []).filter(Boolean);
    if (picked.length === 0) return base;
    return `${base}\n\n（配角设定：${picked.join("、")}）`;
  })();
  if (runMode === "optimize_suggestions") {
    const dir = pendingOptimizeDirection.value.trim();
    if (dir) {
      mergedTask = `${mergedTask}\n\n【作者对优化方向的要求】\n${dir}`;
    }
    pendingOptimizeDirection.value = "";
  }
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
    current_map: (form.currentMap || "").trim() || null,
    lore_tags:
      runMode === "optimize_suggestions" && loreTags.length === 0 ? null : loreTags,
    structure_card: null,
    structure_risk_ack: false,
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
  const mode0 = String(payload.mode || "");
  currentStreamMode.value = mode0;
  const isInitRun = mode0 === "init_state";
  if (mode0 === "init_state") {
    runPhase.value = "world_init";
    runHint.value = "正在生成本书世界观…";
    worldInitError.value = "";
    worldInitDialogVisible.value = true;
    worldInitStreamText.value = "";
    resultText.value = "本书世界观初始化输出在独立窗口中显示（见「本书世界观初始化」弹窗）。";
  } else {
    runPhase.value = "planning";
    runHint.value = "已提交任务，正在排队/规划...";
  }
  lastOutputPath.value = "";
  tokenUsageText.value = "";
  shadowDigestText.value = "";
  consistencyAuditText.value = "";
  consistencyAuditSeverity.value = "ok";
  nextStatusText.value = "";
  planStreamText.value = "";
  try {
    const startAt = Date.now();
    let logText = "（流式输出开始）\n";
    let accContent = "";
    let donePayload: Record<string, unknown> | null = null;
    const refreshStreamText = () => {
      const block = `${logText}\n\n[content]\n${accContent}`;
      if (isInitRun) {
        worldInitStreamText.value = block;
      } else {
        resultText.value = block;
      }
    };

    await apiSse(`/api/novels/${novelId}/run_stream`, "POST", payload, (evt) => {
      const d = evt.data as Record<string, unknown> | null | undefined;
      if (evt.event === "phase") {
        const name = String(d?.name || "running");
        if (name === "world_init" || name === "running") {
          runPhase.value = "world_init";
          runHint.value = "正在生成本书世界观…";
          rightTab.value = "result";
        }
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
        if (isInitRun) {
          worldInitError.value = String(msg);
        }
        logText += `\n[error]\n${msg}\n`;
        refreshStreamText();
      } else if (evt.event === "done") {
        donePayload = (d || null) as Record<string, unknown> | null;
        runPhase.value = "done";
        runHint.value = "本次任务已完成";
      }
    }, runAbortController.signal);

    if (donePayload) {
      const modeStr = String(donePayload.mode || "");
      if (modeStr === "init_state") {
        worldInitError.value = "";
        loadTags().catch(() => {});
      }
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

      const blockedByStructure = Boolean(donePayload.blocked) && String(donePayload.block_type || "") === "structure_gate";
      if (blockedByStructure) {
        const gate = (donePayload.structure_gate || null) as Record<string, unknown> | null;
        previewStructureGate.value = gate;
        const msg = String(gate?.risk_message || "结构卡未满足最小项，已阻断本次生成。").trim();
        runHint.value = "结构卡最小项未满足，请补齐后再试。";
        ElMessage.warning(msg);
        return;
      }

      const modesWithNextChapterHint = new Set([
        "write_chapter",
        "revise_chapter",
        "expand_chapter",
        "optimize_suggestions",
      ]);
      const auditObj = (donePayload.consistency_audit || null) as Record<string, unknown> | null;
      const blockReasons = Array.isArray(auditObj?.block_reasons)
        ? (auditObj?.block_reasons as Array<Record<string, unknown>>)
        : [];
      const blockedNextChapterHint = blockReasons.length > 0;
      if (modesWithNextChapterHint.has(modeStr)) {
        if (blockedNextChapterHint) {
          const first = String(blockReasons[0]?.message || "").trim();
          runHint.value = "一致性审计发现高危冲突，已暂停自动下章续写。";
          ElMessage.warning(first || "一致性审计发现高危冲突，请先修复后再续写。");
          nextChapterHintVisible.value = false;
        } else {
          const prefill =
            modeStr === "optimize_suggestions"
              ? String(donePayload.content || "").trim()
              : String(donePayload.next_status || "").trim();
          nextChapterHintDraft.value = prefill;
          nextChapterHintVisible.value = true;
        }
      }
      const chTl = String(donePayload.chapter_timeline_event_id || "").trim();
      if (chTl.startsWith("ev:timeline:")) {
        lastChapterTimelineEventId.value = chTl;
      }
      shadowDigestText.value = buildShadowDigest(donePayload, modeStr, chTl);
      const audit = formatConsistencyAudit(donePayload.consistency_audit);
      consistencyAuditText.value = audit.text;
      consistencyAuditSeverity.value = audit.severity;
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
      if (mode0 === "init_state") {
        worldInitStreamText.value += "\n\n[abort]\n用户已手动中止本次流式生成。\n";
      } else {
        resultText.value += "\n\n[abort]\n用户已手动中止本次流式生成。\n";
      }
    } else {
      runPhase.value = "error";
      runHint.value = "执行失败，请查看错误信息";
      ElMessage.error(`运行失败：${err?.message || String(e)}`);
    }
  } finally {
    running.value = false;
    runAbortController = null;
    currentStreamMode.value = "";
  }
}

function formatConsistencyAudit(raw: unknown): { text: string; severity: "ok" | "warn" | "high" } {
  if (!raw || typeof raw !== "object") return { text: "", severity: "ok" };
  const x = raw as {
    score?: unknown;
    severity?: unknown;
    issue_count?: unknown;
    block_reasons?: Array<{ message?: unknown }>;
    recommended_actions?: Array<unknown>;
    issues?: Array<{ level?: unknown; message?: unknown; suggestion?: unknown }>;
  };
  const sev = String(x.severity || "ok");
  const severity: "ok" | "warn" | "high" = sev === "high" ? "high" : sev === "warn" ? "warn" : "ok";
  const score = Number(x.score ?? NaN);
  const issueCount = Number(x.issue_count ?? 0);
  const issues = Array.isArray(x.issues) ? x.issues : [];
  const lines: string[] = [];
  lines.push(`评分：${Number.isFinite(score) ? score : "-"} / 100`);
  lines.push(`问题数：${Number.isFinite(issueCount) ? issueCount : issues.length}`);
  if (!issues.length) {
    lines.push("未发现明显一致性问题。");
  } else {
    const top = issues.slice(0, 4);
    for (const it of top) {
      const lvl = String(it?.level || "warn").toUpperCase();
      const msg = String(it?.message || "").trim();
      const sug = String(it?.suggestion || "").trim();
      if (msg) lines.push(`[${lvl}] ${msg}`);
      if (sug) lines.push(`  建议：${sug}`);
    }
    if (issues.length > top.length) {
      lines.push(`... 另有 ${issues.length - top.length} 条，可在后端返回中查看详情。`);
    }
  }
  const br = Array.isArray(x.block_reasons) ? x.block_reasons : [];
  if (br.length > 0) {
    lines.push("阻断原因：");
    for (const it of br.slice(0, 3)) {
      const msg = String(it?.message || "").trim();
      if (msg) lines.push(`- ${msg}`);
    }
  }
  const acts = Array.isArray(x.recommended_actions) ? x.recommended_actions : [];
  if (acts.length > 0) {
    lines.push("修复动作：");
    for (const a of acts.slice(0, 3)) {
      const txt = String(a || "").trim();
      if (txt) lines.push(`- ${txt}`);
    }
  }
  return { text: lines.join("\n"), severity };
}

function buildShadowDigest(
  donePayload: Record<string, unknown>,
  modeStr: string,
  chapterTimelineEventId: string
): string {
  const blocks: string[] = [];
  if (modeStr) blocks.push(`模式：${modeStr}`);
  const chapterIndex = donePayload.chapter_index;
  if (chapterIndex != null && chapterIndex !== "") blocks.push(`章节：${String(chapterIndex)}`);
  if (chapterTimelineEventId) blocks.push(`事件归属：${chapterTimelineEventId}`);
  const plan = donePayload.plan as Record<string, unknown> | null | undefined;
  if (plan && typeof plan === "object") {
    const beats = Array.isArray(plan.beats) ? plan.beats.length : 0;
    if (beats > 0) blocks.push(`规划节拍：${beats} 条`);
    const timeSlot = String(plan.time_slot || "").trim();
    if (timeSlot) blocks.push(`时间段：${timeSlot}`);
  }
  const nextStatus = String(donePayload.next_status || "").trim();
  if (nextStatus) {
    const short = nextStatus.length > 160 ? `${nextStatus.slice(0, 160)}...` : nextStatus;
    blocks.push(`下章建议摘要：${short}`);
  }
  return blocks.join("\n");
}

function runInitWorld() {
  return startPreviewRun("init_state");
}

async function startPreviewRun(runMode: AppRunMode): Promise<boolean> {
  const built = buildRunPayload(runMode);
  if (!built) return false;
  suggestedTimelineEventId.value = "";
  suggestedTimelineEventLabel.value = "";
  previewStructureGate.value = null;
  previewingInput.value = true;
  runPhase.value = "idle";
  runHint.value = "正在生成预览…";
  try {
    const data = await apiJson(
      `/api/novels/${encodeURIComponent(built.novelId)}/preview_input`,
      "POST",
      built.payload
    );
    const asObj = data as Record<string, unknown>;
    suggestedTimelineEventId.value = String(asObj?.suggested_timeline_event_id || "").trim();
    suggestedTimelineEventLabel.value = String(asObj?.suggested_timeline_event_label || "").trim();
    previewStructureGate.value =
      asObj?.structure_gate && typeof asObj.structure_gate === "object"
        ? (asObj.structure_gate as Record<string, unknown>)
        : null;
    setInputPreviewFromApi(data);
    const nextPayload = { ...(built.payload as Record<string, unknown>) };
    if (previewStructureGate.value) {
      nextPayload.structure_card =
        (previewStructureGate.value.card as Record<string, unknown> | undefined) || null;
      nextPayload.structure_risk_ack = false;
    }
    pendingRunPayload.value = nextPayload;
    pendingRunNovelId.value = built.novelId;
    runHint.value = "预览已生成，请在弹窗点击「确认并运行」";
    inputPreviewVisible.value = true;
    return true;
  } catch (e: unknown) {
    const err = e as { message?: string };
    ElMessage.error(`预览生成失败：${err?.message || String(e)}`);
    return false;
  } finally {
    previewingInput.value = false;
  }
}

function applySuggestedTimelineEvent() {
  const eid = (suggestedTimelineEventId.value || "").trim();
  if (!eid.startsWith("ev:timeline:")) {
    ElMessage.warning("当前没有可采用的事件建议。");
    return;
  }
  form.eventMode = "existing";
  form.existingEventId = eid;
  form.newEventTimeSlot = "";
  form.newEventSummary = "";
  form.newEventPrevId = "";
  form.newEventNextId = "";
  ElMessage.success("已采用影子编导建议事件。");
}

function runGenerate() {
  return startPreviewRun("write_chapter");
}
function runExpand() {
  return startPreviewRun("expand_chapter");
}
function runOptimize() {
  const novelId = (form.novelId || "").trim();
  if (!novelId) {
    ElMessage.error("请先选择或创建小说。");
    return;
  }
  if (!(form.userTask || "").trim()) {
    ElMessage.error("请先在「本章任务」中填写待优化的正文或说明。");
    return;
  }
  optimizeIntentDraft.value = "";
  optimizeIntentVisible.value = true;
}

async function confirmOptimizeIntent() {
  pendingOptimizeDirection.value = (optimizeIntentDraft.value || "").trim();
  optimizeIntentVisible.value = false;
  const ok = await startPreviewRun("optimize_suggestions");
  if (!ok) {
    pendingOptimizeDirection.value = "";
  }
}
async function confirmRunFromPreview() {
  if (!pendingRunPayload.value || !pendingRunNovelId.value) {
    ElMessage.error("没有可运行的预览，请先生成预览。");
    return;
  }
  pendingRunStarting.value = true;
  runHint.value = "已确认，准备开始运行...";
  inputPreviewVisible.value = false;
  try {
    const payload = { ...(pendingRunPayload.value as Record<string, unknown>) };
    payload.structure_risk_ack = false;
    await executeRun(
      pendingRunNovelId.value,
      payload
    );
  } finally {
    pendingRunStarting.value = false;
    userTaskBeforePreviewFromNextChapter.value = null;
  }
}

async function confirmRunFromPreviewRisk() {
  if (!pendingRunPayload.value || !pendingRunNovelId.value) {
    ElMessage.error("没有可运行的预览，请先生成预览。");
    return;
  }
  pendingRunStarting.value = true;
  runHint.value = "已确认风险，准备开始运行...";
  inputPreviewVisible.value = false;
  try {
    const payload = { ...(pendingRunPayload.value as Record<string, unknown>) };
    payload.structure_risk_ack = true;
    await executeRun(pendingRunNovelId.value, payload);
  } finally {
    pendingRunStarting.value = false;
    userTaskBeforePreviewFromNextChapter.value = null;
  }
}

async function fetchLatestChapterTimelineEventId(): Promise<string> {
  const novelId = (form.novelId || "").trim();
  if (!novelId) return "";
  try {
    const st = (await apiJson(
      `/api/novels/${encodeURIComponent(novelId)}/state`,
      "GET",
      null
    )) as { meta?: { current_chapter_index?: number } };
    const idx = st?.meta?.current_chapter_index;
    if (idx == null || typeof idx !== "number" || idx < 1) return "";
    const ch = (await apiJson(
      `/api/novels/${encodeURIComponent(novelId)}/chapters/${idx}`,
      "GET",
      null
    )) as { timeline_event_id?: string | null };
    const tid = String(ch?.timeline_event_id || "").trim();
    return tid.startsWith("ev:timeline:") ? tid : "";
  } catch {
    return "";
  }
}

async function confirmNextChapterFromHint() {
  const t = String(nextChapterHintDraft.value || "").trim();
  if (!t) {
    ElMessage.error("请填写下章提示。");
    return;
  }
  let bindId = (lastChapterTimelineEventId.value || "").trim();
  if (!bindId.startsWith("ev:timeline:")) {
    bindId = await fetchLatestChapterTimelineEventId();
  }
  if (bindId.startsWith("ev:timeline:")) {
    form.eventMode = "existing";
    form.existingEventId = bindId;
    form.newEventTimeSlot = "";
    form.newEventSummary = "";
    form.newEventPrevId = "";
    form.newEventNextId = "";
  } else if (!(form.eventMode === "existing" && (form.existingEventId || "").trim())) {
    ElMessage.error("未能自动绑定与本章相同的时间线事件，请在「时序」选择「归属到已有事件」后再生成下一章。");
    return;
  }
  userTaskBeforePreviewFromNextChapter.value = form.userTask;
  form.userTask = t;
  nextChapterHintVisible.value = false;
  const started = await startPreviewRun("write_chapter");
  if (!started) {
    form.userTask = userTaskBeforePreviewFromNextChapter.value;
    userTaskBeforePreviewFromNextChapter.value = null;
    nextChapterHintVisible.value = true;
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
    try {
      if (!localStorage.getItem(FIRST_RUN_KEY)) {
        firstRunHintVisible.value = true;
      }
    } catch {
      firstRunHintVisible.value = true;
    }
    await fetchSettingsPaths();
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
    lastChapterTimelineEventId.value = "";
    suggestedTimelineEventId.value = "";
    suggestedTimelineEventLabel.value = "";
    previewStructureGate.value = null;
    await loadAnchors();
    await loadCharacterOptions();
  }
);

watch(inputPreviewVisible, (visible, prevVisible) => {
  if (prevVisible && !visible && userTaskBeforePreviewFromNextChapter.value !== null) {
    if (!pendingRunStarting.value) {
      form.userTask = userTaskBeforePreviewFromNextChapter.value;
      userTaskBeforePreviewFromNextChapter.value = null;
    }
  }
});
</script>

<style scoped>
.app-header-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.app-header-titles {
  min-width: 0;
  flex: 1;
  text-align: center;
}
.app-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.first-run-alert {
  margin-bottom: 16px;
}
.first-run-list {
  margin: 8px 0 0;
  padding-left: 1.25em;
  line-height: 1.65;
}
.first-run-list code {
  font-size: 12px;
}
.first-run-muted {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--lit-ink-muted, #606266);
}
.wrap {
  width: 100%;
  max-width: 1480px;
  margin: 0 auto;
  box-sizing: border-box;
  min-width: 0;
}
.main-layout {
  display: flex;
  gap: 12px;
  align-items: stretch;
  width: 100%;
  min-width: 0;
}
.main-layout--stack {
  flex-direction: column;
}
.main-layout--stack .resize-handle {
  display: none;
}
.main-layout--stack .left-pane,
.main-layout--stack .mid-pane,
.main-layout--stack .right-pane {
  width: 100% !important;
  max-width: 100%;
  min-width: 0 !important;
  flex: 0 0 auto !important;
}
.left-pane {
  flex: 0 0 auto;
  min-width: 0;
  box-sizing: border-box;
}
.mid-pane {
  flex: 0 0 auto;
  min-width: 0;
  box-sizing: border-box;
}
.right-pane {
  flex: 1 1 0;
  min-width: 0;
  box-sizing: border-box;
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
