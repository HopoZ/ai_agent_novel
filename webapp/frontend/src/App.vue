<template>
  <div class="wrap">
    <h2 class="header">AI 小说创作代理（稳定写小说）</h2>

    <div class="main-layout">
      <!-- 左：设定标签 -->
      <div class="left-pane" :style="{ width: `${leftPanelWidth}px` }">
        <el-card class="panel" shadow="never">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <div style="font-weight:600;">设定标签</div>
            <span class="muted">可勾选 / 预览摘要</span>
          </div>

          <el-divider></el-divider>

          <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:8px;">
            <el-button size="small" @click="selectAll">全选</el-button>
            <el-button size="small" @click="invertSelect">反选</el-button>
            <el-button size="small" type="warning" @click="clearSelect">清空</el-button>
            <el-button size="small" type="primary" :loading="buildingLoreSummary" @click="buildCurrentLoreSummary">
              生成当前Tag摘要
            </el-button>
          </div>

          <div v-if="tagsLoading" style="color:#909399;">正在加载设定文件...</div>
          <div v-else class="tag-list-scroll">
            <el-tree
              ref="tagTreeRef"
              class="tag-tree"
              node-key="id"
              :data="tagTreeData"
              :props="{ label: 'label', children: 'children' }"
              show-checkbox
              default-expand-all
              @check="onTreeCheck"
            >
              <template #default="{ data }">
                <div class="tree-node-row">
                  <span class="tree-node-label">{{ data.label }}</span>
                  <template v-if="data.isLeaf && data.tag">
                    <el-popover
                      placement="right"
                      trigger="hover"
                      :open-delay="2000"
                      width="520"
                      popper-class="tag-popover"
                    >
                      <template #default>
                        <div class="preview-scroll">
                          <pre class="tag-preview" v-text="getTagPreview(data.tag)"></pre>
                        </div>
                      </template>
                      <template #reference>
                        <el-button
                          size="small"
                          link
                          type="primary"
                          @click.stop
                        >
                          预览摘要
                        </el-button>
                      </template>
                    </el-popover>
                    <el-button
                      size="small"
                      link
                      type="primary"
                      @click.stop.prevent="openTagDialog(data.tag)"
                    >
                      详情
                    </el-button>
                  </template>
                </div>
              </template>
            </el-tree>
          </div>

          <div class="tag-hint">
            建议至少勾选 1 项；不勾选会导致设定为空，可能无法生成状态/正文。
          </div>
        </el-card>
      </div>

      <div class="resize-handle" @mousedown="startResizeLeft" title="拖动调整左侧宽度"></div>

      <!-- 中：填写字段 -->
      <div class="mid-pane">
        <el-card class="panel" shadow="never">
          <el-form label-position="top">
            <div style="font-weight:600;">已有小说</div>
            <div class="muted" style="margin-top:4px;">
              选择后会切换当前上下文（锚点/图谱/运行都基于当前小说）。
            </div>
            <div style="height:8px;"></div>

            <el-form-item label="选择已有小说">
              <el-select
                v-model="form.novelId"
                :loading="novelsLoading"
                clearable
                placeholder="请选择已有小说（显示小说名）"
                style="width:100%;"
              >
                <el-option
                  v-for="n in novels"
                  :key="n.novel_id"
                  :label="n.novel_title"
                  :value="n.novel_id"
                />
              </el-select>
            </el-form-item>

            <el-form-item label="当前小说名（只读）">
              <el-input :model-value="currentNovelTitle" disabled></el-input>
            </el-form-item>

            <el-form-item>
              <el-button style="width:100%;" @click="openCreateDialog" :disabled="running">
                新建小说（弹窗）
              </el-button>
            </el-form-item>

            <el-divider></el-divider>

            <el-form-item label="模式">
              <el-select v-model="form.mode" placeholder="选择运行模式">
                <el-option label="生成本章初始人物/世界状态" value="init_state" />
                <el-option label="只生成本章要点并更新世界状态" value="plan_only" />
                <el-option label="生成正文并更新世界状态" value="write_chapter" />
                <el-option label="修订指定章节（MVP：仍走规划+写作）" value="revise_chapter" />
              </el-select>
            </el-form-item>

            <el-form-item label="插入位置 / 时间段（二选一）">
              <el-radio-group v-model="form.insertMode" class="choice-cards">
                <el-radio-button label="anchors">插入到事件网（选择锚点）</el-radio-button>
                <el-radio-button label="time">手动填写时间段</el-radio-button>
              </el-radio-group>
              <div class="muted" style="margin-top:6px;">
                二选一：选“插入到事件网”则按锚点推导时间段；选“手动时间段”则忽略锚点。
              </div>
            </el-form-item>

            <template v-if="form.insertMode === 'anchors'">
              <el-form-item label="插入在这件事之后（可选）">
                <el-select
                  v-model="form.insertAfterId"
                  :loading="anchorsLoading"
                  clearable
                  placeholder="选择一件“之前发生的事”作为下界（after）"
                  style="width:100%;"
                >
                  <el-option v-for="a in anchors" :key="a.id" :label="a.label" :value="a.id" />
                </el-select>
              </el-form-item>

              <el-form-item label="插入在这件事之前（可选）">
                <el-select
                  v-model="form.insertBeforeId"
                  :loading="anchorsLoading"
                  clearable
                  placeholder="选择一件“之后发生的事”作为上界（before）"
                  style="width:100%;"
                >
                  <el-option v-for="a in anchors" :key="a.id" :label="a.label" :value="a.id" />
                </el-select>
                <div class="muted" style="margin-top:6px;">
                  推导时间段：{{ inferredTimeSlotHint || "（未选择锚点：将自动延续到最新进度）" }}
                </div>
              </el-form-item>
            </template>

            <template v-else>
              <el-form-item label="时间段覆盖（手动）">
                <el-input v-model="form.timeSlotOverride" placeholder="例如：第三年秋·傍晚 / 第七日清晨 / 某个具体阶段"></el-input>
              </el-form-item>
            </template>

            <el-form-item label="主视角覆盖（可多选）">
              <el-select
                v-model="form.povCharacterOverride"
                multiple
                collapse-tags
                collapse-tags-tooltip
                clearable
                filterable
                allow-create
                default-first-option
                placeholder="多选表示与本章最相关的核心人物"
                style="width:100%;"
                @change="onPovChange"
              >
                <el-option v-for="cid in allCharacterOptions" :key="cid" :label="cid" :value="cid" />
              </el-select>
            </el-form-item>
            <el-form-item label="快速多选角色（配角设定）">
              <el-select
                v-model="form.focusCharacterIds"
                multiple
                collapse-tags
                collapse-tags-tooltip
                clearable
                filterable
                allow-create
                default-first-option
                placeholder="点击快速多选作为配角设定（可清空）"
                style="width:100%;"
                @change="onFocusChange"
              >
                <el-option v-for="cid in allCharacterOptions" :key="`focus-${cid}`" :label="cid" :value="cid" />
              </el-select>
            </el-form-item>
            <el-form-item label="角色标签管理（本次会话）">
              <div style="display:flex; gap:8px; width:100%;">
                <el-input v-model="characterTagDraft" placeholder="输入角色标签后点“添加”"></el-input>
                <el-button @click="addCharacterTag">添加</el-button>
              </div>
              <div style="margin-top:8px; display:flex; gap:6px; flex-wrap:wrap;">
                <el-tag
                  v-for="cid in allCharacterOptions"
                  :key="`mg-${cid}`"
                  closable
                  @close="removeCharacterTag(cid)"
                >
                  {{ cid }}
                </el-tag>
              </div>
              <div class="muted" style="margin-top:6px;">
                支持新增/删除角色标签；如需“修改”，先删除旧标签再添加新标签。主视角可多选，快速多选用于配角设定。
              </div>
            </el-form-item>
            <el-form-item label="章节预设名（可选）">
              <el-input v-model="form.chapterPresetName" placeholder="例如：重逢夜 / 石碑共鸣 / 古墟初探"></el-input>
            </el-form-item>

            <el-form-item label="本章任务描述">
              <el-input
                v-model="form.userTask"
                type="textarea"
                :rows="7"
                placeholder="例如：写第3章，主角与某势力冲突，要求推进世界线并更新人物关系。"
              ></el-input>
            </el-form-item>

            <el-form-item>
              <div style="display:flex; gap:8px; width:100%;">
                <el-button type="primary" style="flex:1;" @click="runMode" :loading="running">
                  {{ running ? "运行中..." : "运行模式" }}
                </el-button>
                <el-button style="flex:1;" @click="previewCurrentInput" :loading="previewingInput" :disabled="running">
                  查看当前 Input
                </el-button>
              </div>
            </el-form-item>
          </el-form>
        </el-card>
      </div>

      <!-- 右：输出 -->
      <div class="right-pane">
        <el-card shadow="never">
          <div style="display:flex; gap:8px; align-items:baseline; flex-wrap:wrap;">
            <div style="font-weight:600;">运行结果</div>
            <div class="muted" style="font-size:12px;">会自动显示 state.continuity / content / plan 等</div>
          </div>
          <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-top:8px;">
            <el-tag size="small" :type="running ? 'warning' : (runPhase === 'error' ? 'danger' : 'success')">
              {{ running ? `进行中：${runPhaseLabel}` : `状态：${runPhaseLabel}` }}
            </el-tag>
            <span class="muted" v-if="runHint">{{ runHint }}</span>
          </div>
          <div v-if="tokenUsageText" class="output-path-tip">
            本次 Token：<code>{{ tokenUsageText }}</code>
          </div>
          <div v-if="initTokenUsageText" class="output-path-tip">
            初始化 Token：<code>{{ initTokenUsageText }}</code>
          </div>
          <div v-if="lastOutputPath" class="output-path-tip">
            输出文件：<code>{{ lastOutputPath }}</code>
          </div>
          <el-divider></el-divider>
          <el-tabs v-model="rightTab" class="right-tabs">
            <el-tab-pane label="文本输出" name="result">
              <pre class="result-pre" v-text="resultText"></pre>
            </el-tab-pane>
            <el-tab-pane label="图谱可视化" name="graph">
              <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
                <el-segmented
                  v-model="graphView"
                  :options="[
                    { label: '人物关系网', value: 'people' },
                    { label: '剧情事件网', value: 'events' },
                    { label: '混合网', value: 'mixed' },
                  ]"
                />
                <el-button size="small" :loading="graphLoading" @click="loadGraph">刷新图谱</el-button>
                <span class="muted">点击节点可查看详情</span>
              </div>
              <div style="height:10px;"></div>
              <div class="graph-box">
                <div v-if="!form.novelId" style="color:#909399;">请先选择/创建小说，再查看图谱。</div>
                <div v-else ref="graphEl" class="graph-canvas"></div>
              </div>
            </el-tab-pane>
          </el-tabs>
        </el-card>
      </div>
    </div>
  </div>

  <el-dialog v-model="dialogVisible" :title="dialogTitle" width="70%">
    <div class="dialog-body">
      <pre class="dialog-pre" v-text="dialogText"></pre>
    </div>
    <template #footer>
      <span class="dialog-footer">
        <el-button @click="dialogVisible = false">关闭</el-button>
      </span>
    </template>
  </el-dialog>

  <el-dialog v-model="createDialogVisible" title="创建新小说" width="560px">
    <el-form label-position="top">
      <el-form-item label="新小说名">
        <el-input v-model="createForm.novelTitle" placeholder="例如：无尽深渊纪事"></el-input>
      </el-form-item>
      <el-form-item label="起始时间段（可选）">
        <el-input v-model="createForm.startTimeSlot" placeholder="例如：第三年秋·傍晚 / 第七日清晨"></el-input>
      </el-form-item>
      <el-form-item label="起始视角角色（可选）">
        <el-input v-model="createForm.povCharacterId" placeholder="例如：主角名/角色ID（按你的设定文本）"></el-input>
      </el-form-item>
      <div class="muted" style="margin-top:6px;">
        使用左侧“设定标签”的当前勾选作为本小说 lorebook。
      </div>
    </el-form>
    <template #footer>
      <span class="dialog-footer">
        <el-button @click="createDialogVisible = false" :disabled="running">取消</el-button>
        <el-button type="primary" @click="createNovel" :loading="running">
          {{ running ? "创建中..." : "创建并切换" }}
        </el-button>
      </span>
    </template>
  </el-dialog>

  <el-dialog v-model="inputPreviewVisible" title="当前模型 Input 预览" width="78%">
    <div class="dialog-body">
      <pre class="dialog-pre" v-text="inputPreviewText"></pre>
    </div>
    <template #footer>
      <span class="dialog-footer">
        <el-button @click="inputPreviewVisible = false">关闭</el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script lang="ts" setup>
import { computed, nextTick, onMounted, onBeforeUnmount, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import * as echarts from "echarts";

type Mode = "init_state" | "plan_only" | "write_chapter" | "revise_chapter";

const tagsLoading = ref(true);
const tags = ref<string[]>([]);
const tagGroups = ref<Record<string, string[]>>({});
const selectedTags = ref<string[]>([]);
const tagTreeRef = ref<any>(null);
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
const resultText = ref("等待你的操作...");
const runPhase = ref<"idle" | "planning" | "auto_init" | "writing" | "saving" | "outputs_written" | "done" | "error">("idle");
const runHint = ref("");
const lastOutputPath = ref("");
const initTokenUsageText = ref("");
const tokenUsageText = ref("");
const leftPanelWidth = ref(360);
const LEFT_MIN_WIDTH = 280;
const LEFT_MAX_WIDTH = 680;
let resizingLeft = false;
let resizeStartX = 0;
let resizeStartW = 0;

const rightTab = ref<"result" | "graph">("result");
const graphView = ref<"people" | "events" | "mixed">("mixed");
const graphLoading = ref(false);
const graphEl = ref<HTMLDivElement | null>(null);
let graphChart: echarts.ECharts | null = null;
const graphData = ref<{ nodes: any[]; edges: any[] } | null>(null);

const dialogVisible = ref(false);
const dialogTitle = ref("");
const dialogText = ref("");

const createDialogVisible = ref(false);
const previewingInput = ref(false);
const inputPreviewVisible = ref(false);
const inputPreviewText = ref("");

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

const form = reactive<{
  novelId: string;
  mode: Mode;
  insertMode: "anchors" | "time";
  insertAfterId: string;
  insertBeforeId: string;
  timeSlotOverride: string;
  povCharacterOverride: string[];
  focusCharacterIds: string[];
  chapterPresetName: string;
  userTask: string;
}>({
  novelId: "",
  mode: "write_chapter",
  insertMode: "anchors",
  insertAfterId: "",
  insertBeforeId: "",
  timeSlotOverride: "",
  povCharacterOverride: [],
  focusCharacterIds: [],
  chapterPresetName: "",
  userTask: "",
});

const inferredTimeSlotHint = computed(() => {
  const byId = new Map((anchors.value || []).map((a) => [a.id, a]));
  const after = form.insertAfterId ? byId.get(form.insertAfterId)?.time_slot : "";
  const before = form.insertBeforeId ? byId.get(form.insertBeforeId)?.time_slot : "";
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
  if (p === "auto_init") return "正在自动初始化状态";
  if (p === "writing") return "正在生成正文";
  if (p === "saving") return "正在保存章节与状态";
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

function logDebug(msg: string) {
  // 不在页面展示，仅输出到控制台便于排查
  console.log("[debug]", msg);
}

function onLeftResizeMove(e: MouseEvent) {
  if (!resizingLeft) return;
  const delta = e.clientX - resizeStartX;
  const next = Math.max(LEFT_MIN_WIDTH, Math.min(LEFT_MAX_WIDTH, resizeStartW + delta));
  leftPanelWidth.value = next;
}

function onLeftResizeUp() {
  if (!resizingLeft) return;
  resizingLeft = false;
  window.removeEventListener("mousemove", onLeftResizeMove);
  window.removeEventListener("mouseup", onLeftResizeUp);
}

function startResizeLeft(e: MouseEvent) {
  resizingLeft = true;
  resizeStartX = e.clientX;
  resizeStartW = leftPanelWidth.value;
  window.addEventListener("mousemove", onLeftResizeMove);
  window.addEventListener("mouseup", onLeftResizeUp);
}

async function apiJson(url: string, method: string, body: any) {
  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let data: any = null;
  try {
    data = JSON.parse(text);
  } catch {
    data = { raw: text };
  }
  if (!res.ok) {
    const msg = data && data.detail ? data.detail : JSON.stringify(data);
    logDebug(`API error: ${method} ${url} -> ${res.status} ${msg}`);
    throw new Error(msg);
  }
  return data;
}

async function apiSse(url: string, method: string, body: any, onEvent: (evt: { event: string; data: any }) => void) {
  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `HTTP ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buf = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    buf = buf.replace(/\r\n/g, "\n");

    // SSE events are separated by \n\n
    while (true) {
      const idx = buf.indexOf("\n\n");
      if (idx === -1) break;
      const raw = buf.slice(0, idx);
      buf = buf.slice(idx + 2);

      const lines = raw.split("\n").map((l) => l.trimEnd());
      let evName = "message";
      let dataLine = "";
      for (const ln of lines) {
        if (ln.startsWith("event:")) evName = ln.slice("event:".length).trim();
        if (ln.startsWith("data:")) dataLine += ln.slice("data:".length).trim();
      }
      if (!dataLine) continue;
      try {
        const parsed = JSON.parse(dataLine);
        onEvent({ event: evName, data: parsed?.data });
      } catch {
        onEvent({ event: evName, data: { raw: dataLine } });
      }
    }
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
  const res = await apiJson("/api/lore/tags", "GET", null);
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
    const res = await apiJson("/api/lore/summary/build", "POST", { tags: tagsNow, force: true });
    const rows = Array.isArray(res?.tag_summaries) ? res.tag_summaries : [];
    const text = rows.length
      ? rows
          .map((x: any) => `【${String(x?.tag || "")}】\n${String(x?.summary || "")}`)
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
    const res = await apiJson("/api/novels", "GET", null);
    novels.value = res.novels || [];

    // 没选中的情况下，自动选中最新一部
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
  form.insertAfterId = "";
  form.insertBeforeId = "";
  form.insertMode = "anchors";
  if (!novelId) return;
  anchorsLoading.value = true;
  try {
    const res = await apiJson(`/api/novels/${encodeURIComponent(novelId)}/anchors`, "GET", null);
    anchors.value = res.anchors || [];
  } catch (e: any) {
    logDebug("loadAnchors failed: " + (e?.message || String(e)));
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
    const st = await apiJson(`/api/novels/${encodeURIComponent(novelId)}/state`, "GET", null);
    const list = Array.isArray(st?.characters) ? st.characters : [];
    const ids = list
      .map((c: any) => String(c?.character_id || "").trim())
      .filter((x: string) => !!x);
    characterOptions.value = Array.from(new Set(ids));
  } catch (e: any) {
    logDebug("loadCharacterOptions failed: " + (e?.message || String(e)));
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

function onPovChange(v: any) {
  const arr = Array.isArray(v) ? v : [];
  for (const item of arr) {
    const key = String(item || "").trim();
    if (!key) continue;
    if (!allCharacterOptions.value.includes(key)) customCharacterOptions.value.push(key);
    hiddenCharacterOptions.value = hiddenCharacterOptions.value.filter((x) => x !== key);
  }
}

function onFocusChange(v: any) {
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
  const res = await apiJson(url, "GET", null);
  previewCache[tag] = (res && res.preview) ? res.preview : "";
  logDebug(`Loaded preview tag=${tag} len=${previewCache[tag].length}`);
}

async function loadPreviewFull(tag: string) {
  if (Object.prototype.hasOwnProperty.call(previewFullCache, tag)) return;
  const url = `/api/lore/preview?tag=${encodeURIComponent(tag)}&max_chars=0&compact=0`;
  const res = await apiJson(url, "GET", null);
  previewFullCache[tag] = (res && res.preview) ? res.preview : "";
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

function formatResponse(data: any) {
  const header = [
    `mode=${data.mode}, chapter_index=${data.chapter_index}`,
    `state_updated=${data.state_updated}`,
    data.usage_metadata ? `usage=${JSON.stringify(data.usage_metadata)}` : "",
  ].filter(Boolean).join("\n");

  const continuity =
    data.state && data.state.continuity ? JSON.stringify(data.state.continuity, null, 2) : "";
  const stateTail = continuity ? `\n\n[continuity]\n${continuity}` : "";

  const content = data.content ? `\n\n[content]\n${data.content}` : "";
  const plan = data.plan ? `\n\n[plan]\n${JSON.stringify(data.plan, null, 2)}` : "";
  return header + stateTail + content + plan;
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
  const res = await apiJson("/api/novels", "POST", payload);
  form.novelId = res.novel_id;
  // 清空创建表单，避免与“已有小说”混淆
  createForm.novelTitle = "";
  createForm.startTimeSlot = "";
  createForm.povCharacterId = "";
  // 刷新已有小说列表，确保下拉框能看到新建结果
  await loadNovels();
  await loadAnchors();
  resultText.value = `创建成功！\n\n现在选择运行模式并点击“运行模式”。`;
  createDialogVisible.value = false;
}

async function runMode() {
  const novelId = (form.novelId || "").trim();
  if (!novelId) {
    ElMessage.error("请先创建新小说或填写小说编号。");
    return;
  }

  // 不再强制要求手动 init_state：后端会在需要时自动初始化

  const loreTags = selectedTags.value || [];
  if (loreTags.length === 0) {
    ElMessage.error("请至少勾选 1 项设定（settings/*.md 文件名）。");
    return;
  }
  if (!form.userTask || !form.userTask.trim()) {
    ElMessage.error("请输入本章任务描述（例如：写第3章 + 更新世界线/人物关系的要求）。");
    return;
  }

  running.value = true;
  runPhase.value = "planning";
  runHint.value = "已提交任务，正在排队/规划...";
  lastOutputPath.value = "";
  initTokenUsageText.value = "";
  tokenUsageText.value = "";
  try {
    const mergedTask = (() => {
      const base = form.userTask || "";
      const picked = (form.focusCharacterIds || []).filter(Boolean);
      if (picked.length === 0) return base;
      return `${base}\n\n（配角设定：${picked.join("、")}）`;
    })();
    const payload = {
      mode: form.mode,
      user_task: mergedTask,
      insert_after_id: form.insertMode === "anchors" ? (form.insertAfterId || null) : null,
      insert_before_id: form.insertMode === "anchors" ? (form.insertBeforeId || null) : null,
      time_slot_override: form.insertMode === "time" ? (form.timeSlotOverride || null) : null,
      pov_character_ids_override: (form.povCharacterOverride || []).filter(Boolean),
      supporting_character_ids: (form.focusCharacterIds || []).filter(Boolean),
      chapter_preset_name: form.chapterPresetName || null,
      lore_tags: loreTags,
    };
    // 流式输出：边生成边显示
    const startAt = Date.now();
    let logText = "（流式输出开始）\n";
    let accContent = "";
    let donePayload: any = null;

    await apiSse(`/api/novels/${novelId}/run_stream`, "POST", payload, (evt) => {
      if (evt.event === "phase") {
        const name = String(evt.data?.name || "running");
        if (name === "planning" || name === "auto_init" || name === "writing" || name === "saving" || name === "outputs_written") {
          runPhase.value = name;
        }
        const extra =
          name === "writing" && evt.data?.chapter_index ? ` chapter=${evt.data.chapter_index}` : "";
        const out =
          name === "outputs_written" && evt.data?.path ? ` path=${evt.data.path}` : "";
        if (name === "planning") runHint.value = "正在生成章节规划（beats + next_state）";
        if (name === "auto_init") runHint.value = "检测到未初始化，正在自动初始化世界状态";
        if (name === "writing") runHint.value = "正在流式生成正文，请稍候...";
        if (name === "saving") runHint.value = "正在保存章节记录和世界状态";
        if (name === "auto_init" && evt.data?.usage_metadata) {
          const u = evt.data.usage_metadata || {};
          const input =
            u.input_tokens ?? u.prompt_tokens ?? u.input_token_count ?? null;
          const output =
            u.output_tokens ?? u.completion_tokens ?? u.output_token_count ?? null;
          const total =
            u.total_tokens ?? u.total_token_count ??
            ((typeof input === "number" && typeof output === "number") ? (input + output) : null);
          if (input !== null || output !== null || total !== null) {
            initTokenUsageText.value = `input=${input ?? "-"}, output=${output ?? "-"}, total=${total ?? "-"}`;
            logText += `[usage:auto_init] ${initTokenUsageText.value}\n`;
          }
        }
        if (name === "outputs_written") {
          lastOutputPath.value = String(evt.data?.path || "");
          runHint.value = "正文已归档到 outputs，可在本地打开查看";
        }
        logText += `\n[phase] ${name}${extra}${out}\n`;
        resultText.value = `${logText}\n\n[content]\n${accContent}`;
      } else if (evt.event === "content") {
        const delta = evt.data?.delta || "";
        accContent += delta;
        // 实时刷新正文，同时保留日志
        resultText.value = `${logText}\n\n[content]\n${accContent}`;
      } else if (evt.event === "error") {
        const msg = evt.data?.message || JSON.stringify(evt.data);
        runPhase.value = "error";
        runHint.value = "执行失败，请查看下方错误日志";
        logText += `\n[error]\n${msg}\n`;
        resultText.value = `${logText}\n\n[content]\n${accContent}`;
      } else if (evt.event === "done") {
        donePayload = evt.data;
        runPhase.value = "done";
        runHint.value = "本次任务已完成";
      }
    });

    if (donePayload) {
      // 不要用结构化结果覆盖掉正文；只追加一段“完成摘要”
      const ms = Date.now() - startAt;
      const ch = donePayload.chapter_index ? `chapter_index=${donePayload.chapter_index}` : "chapter_index=(auto)";
      const st = donePayload.state_updated ? "state_updated=true" : "state_updated=false";
      const u = donePayload.usage_metadata || {};
      const input =
        u.input_tokens ?? u.prompt_tokens ?? u.input_token_count ?? null;
      const output =
        u.output_tokens ?? u.completion_tokens ?? u.output_token_count ?? null;
      const total =
        u.total_tokens ?? u.total_token_count ??
        ((typeof input === "number" && typeof output === "number") ? (input + output) : null);
      if (input !== null || output !== null || total !== null) {
        tokenUsageText.value = `input=${input ?? "-"}, output=${output ?? "-"}, total=${total ?? "-"}`;
      }
      logText += `\n[done] ${ch}, ${st}, elapsed_ms=${ms}\n`;
      resultText.value = `${logText}\n\n[content]\n${accContent}`;
    }
    await loadAnchors();
  } finally {
    running.value = false;
  }
}

async function previewCurrentInput() {
  const novelId = (form.novelId || "").trim();
  if (!novelId) {
    ElMessage.error("请先选择/创建小说。");
    return;
  }
  if (!form.userTask || !form.userTask.trim()) {
    ElMessage.error("请先填写本章任务描述。");
    return;
  }
  const loreTags = selectedTags.value || [];
  if (loreTags.length === 0) {
    ElMessage.error("请至少勾选 1 项设定。");
    return;
  }
  previewingInput.value = true;
  try {
    const mergedTask = (() => {
      const base = form.userTask || "";
      const picked = (form.focusCharacterIds || []).filter(Boolean);
      if (picked.length === 0) return base;
      return `${base}\n\n（配角设定：${picked.join("、")}）`;
    })();
    const payload = {
      mode: form.mode,
      user_task: mergedTask,
      insert_after_id: form.insertMode === "anchors" ? (form.insertAfterId || null) : null,
      insert_before_id: form.insertMode === "anchors" ? (form.insertBeforeId || null) : null,
      time_slot_override: form.insertMode === "time" ? (form.timeSlotOverride || null) : null,
      pov_character_ids_override: (form.povCharacterOverride || []).filter(Boolean),
      supporting_character_ids: (form.focusCharacterIds || []).filter(Boolean),
      chapter_preset_name: form.chapterPresetName || null,
      lore_tags: loreTags,
    };
    const data = await apiJson(`/api/novels/${encodeURIComponent(novelId)}/preview_input`, "POST", payload);
    inputPreviewText.value = JSON.stringify(data, null, 2);
    inputPreviewVisible.value = true;
  } finally {
    previewingInput.value = false;
  }
}

function ensureGraphChart() {
  if (!graphEl.value) return;
  if (graphChart) return;
  graphChart = echarts.init(graphEl.value, undefined, { renderer: "canvas" });
  window.addEventListener("resize", onResize);
  graphChart.on("click", (params: any) => {
    if (params?.dataType === "node" && params?.data) {
      const n = params.data;
      dialogTitle.value = `节点详情：${n.label || n.name || n.id}`;
      dialogText.value = JSON.stringify(n, null, 2);
      dialogVisible.value = true;
    }
    if (params?.dataType === "edge" && params?.data) {
      dialogTitle.value = `关系详情：${params.data?.label || ""}`.trim() || "关系详情";
      dialogText.value = JSON.stringify(params.data, null, 2);
      dialogVisible.value = true;
    }
  });
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

function renderGraph() {
  ensureGraphChart();
  if (!graphChart) return;
  const payload = graphData.value;
  if (!payload) {
    graphChart.clear();
    return;
  }

  const nodes = (payload.nodes || []).map((n: any) => ({
    ...n,
    name: n.label || n.id,
    symbolSize: n.type === "character" ? 28 : (n.type === "faction" ? 22 : 18),
    itemStyle: { color: typeColor(n.type) },
    draggable: true,
    value: n.type,
  }));
  const links = (payload.edges || []).map((e: any) => ({
    ...e,
    lineStyle: { opacity: 0.7, width: 1.2, curveness: 0.18 },
    label: { show: !!e.label, formatter: e.label },
  }));

  graphChart.setOption(
    {
      tooltip: {
        trigger: "item",
        formatter: (p: any) => {
          if (p.dataType === "node") return `${p.data?.type || ""}：${p.data?.label || p.data?.id}`;
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
}

async function loadGraph() {
  const novelId = (form.novelId || "").trim();
  if (!novelId) {
    ElMessage.error("请先选择/创建小说。");
    return;
  }
  graphLoading.value = true;
  try {
    const url = `/api/novels/${encodeURIComponent(novelId)}/graph?view=${encodeURIComponent(graphView.value)}`;
    const res = await apiJson(url, "GET", null);
    graphData.value = { nodes: res.nodes || [], edges: res.edges || [] };
    await nextTick();
    renderGraph();
  } catch (e: any) {
    ElMessage.error("加载图谱失败：" + (e?.message || String(e)));
  } finally {
    graphLoading.value = false;
  }
}

onMounted(async () => {
  try {
    await loadTags();
    await loadNovels();
    await loadAnchors();
    await loadCharacterOptions();
    await preloadAllPreviews();
  } catch (e: any) {
    tagsLoading.value = false;
    logDebug("loadTags/preload failed: " + (e?.message || String(e)));
  }
});

watch(
  () => form.novelId,
  async () => {
    await loadAnchors();
    await loadCharacterOptions();
  }
);

watch([rightTab, graphView, () => form.novelId], async ([tab]) => {
  if (tab !== "graph") return;
  await nextTick();
  // 切换视图/小说时，必须重新拉取对应 view 的数据
  await loadGraph();
});

onBeforeUnmount(() => {
  onLeftResizeUp();
  window.removeEventListener("resize", onResize);
  if (graphChart) {
    graphChart.dispose();
    graphChart = null;
  }
});
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
  flex: 0 0 420px;
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
  transition: filter 0.2s, background-color 0.2s;
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
.output-path-tip {
  margin-top: 6px;
  font-size: 12px;
  color: #606266;
  word-break: break-all;
}
.result-pre {
  max-height: 48vh;
  overflow: auto;
  padding: 10px;
  background: #fff;
  border-radius: 10px;
  border: 1px solid #ebeef5;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
}
.right-tabs :deep(.el-tabs__content) {
  padding-top: 6px;
}
.graph-box {
  height: 58vh;
  border: 1px solid #ebeef5;
  border-radius: 10px;
  background: #fff;
  overflow: hidden;
}
.graph-canvas {
  width: 100%;
  height: 100%;
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
.dialog-body {
  max-height: 70vh;
  overflow: auto;
  background: #fff;
  padding: 10px;
  border: 1px solid #ebeef5;
  border-radius: 10px;
}
.dialog-pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
}

.choice-cards {
  width: 100%;
}
.choice-cards :deep(.el-radio-button__inner) {
  width: 100%;
}
</style>

