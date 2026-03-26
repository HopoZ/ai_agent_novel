<template>
  <div class="wrap">
    <h2 class="header">AI 小说创作代理（稳定写小说）</h2>

    <el-row :gutter="16">
      <!-- 左：设定标签 -->
      <el-col :span="6">
        <el-card class="panel" shadow="never">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <div style="font-weight:600;">设定标签</div>
            <span class="muted">可勾选 / 悬浮预览</span>
          </div>

          <el-divider></el-divider>

          <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:8px;">
            <el-button size="small" @click="selectAll">全选</el-button>
            <el-button size="small" @click="invertSelect">反选</el-button>
            <el-button size="small" type="warning" @click="clearSelect">清空</el-button>
          </div>

          <div v-if="tagsLoading" style="color:#909399;">正在加载设定文件...</div>
          <div v-else class="tag-list tag-list-scroll">
            <div v-for="tag in tags" :key="tag" class="tag-item">
              <el-popover
                placement="right"
                trigger="hover"
                :open-delay="2000"
                width="520"
                popper-class="tag-popover"
              >
                <template #default>
                  <div class="preview-scroll">
                    <pre class="tag-preview" v-text="getTagPreview(tag)"></pre>
                  </div>
                </template>
                <template #reference>
                  <div style="display:flex; align-items:center; gap:8px;">
                    <el-checkbox-button
                      :checked="selectedTags.includes(tag)"
                      @change="(v:any) => onTagChange(tag, v)"
                    >
                      {{ tag }}
                    </el-checkbox-button>
                    <el-button
                      size="small"
                      link
                      type="primary"
                      @click.stop.prevent="openTagDialog(tag)"
                    >
                      预览
                    </el-button>
                  </div>
                </template>
              </el-popover>
            </div>
          </div>

          <div class="tag-hint">
            建议至少勾选 1 项；不勾选会导致设定为空，可能无法生成状态/正文。
          </div>
        </el-card>
      </el-col>

      <!-- 中：填写字段 -->
      <el-col :span="8">
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

            <el-form-item label="视角角色覆盖（可选）">
              <el-input v-model="form.povCharacterOverride" placeholder="例如：主角名/角色ID（按你的设定文本）"></el-input>
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
              <el-button type="primary" style="width:100%;" @click="runMode" :loading="running">
                {{ running ? "运行中..." : "运行模式" }}
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <!-- 右：输出 -->
      <el-col :span="10">
        <el-card shadow="never">
          <div style="display:flex; gap:8px; align-items:baseline; flex-wrap:wrap;">
            <div style="font-weight:600;">运行结果</div>
            <div class="muted" style="font-size:12px;">会自动显示 state.continuity / content / plan 等</div>
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
      </el-col>
    </el-row>
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
</template>

<script lang="ts" setup>
import { computed, nextTick, onMounted, onBeforeUnmount, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import * as echarts from "echarts";

type Mode = "init_state" | "plan_only" | "write_chapter" | "revise_chapter";

const tagsLoading = ref(true);
const tags = ref<string[]>([]);
const selectedTags = ref<string[]>([]);
const novelsLoading = ref(true);
const novels = ref<Array<{ novel_id: string; novel_title: string }>>([]);
const previewCache = reactive<Record<string, string>>({});

const anchorsLoading = ref(false);
const anchors = ref<Array<{ id: string; label: string; type: string; time_slot: string }>>([]);

const running = ref(false);
const resultText = ref("等待你的操作...");

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
  povCharacterOverride: string;
  userTask: string;
}>({
  novelId: "",
  mode: "write_chapter",
  insertMode: "anchors",
  insertAfterId: "",
  insertBeforeId: "",
  timeSlotOverride: "",
  povCharacterOverride: "",
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

function logDebug(msg: string) {
  // 不在页面展示，仅输出到控制台便于排查
  console.log("[debug]", msg);
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
}
function clearSelect() {
  selectedTags.value = [];
}
function invertSelect() {
  const set = new Set(selectedTags.value);
  selectedTags.value = tags.value.filter((t) => !set.has(t));
}
function onTagChange(tag: string, checked: any) {
  const boolChecked = !!checked;
  const set = new Set(selectedTags.value);
  if (boolChecked) set.add(tag);
  else set.delete(tag);
  selectedTags.value = Array.from(set);
}

async function loadTags() {
  tagsLoading.value = true;
  const res = await apiJson("/api/lore/tags", "GET", null);
  tags.value = res.tags || [];
  selectedTags.value = [...tags.value];
  for (const k of Object.keys(previewCache)) delete previewCache[k];
  tagsLoading.value = false;
  logDebug(`Loaded tags count=${tags.value.length}`);
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

async function loadPreview(tag: string) {
  if (Object.prototype.hasOwnProperty.call(previewCache, tag)) return;
  const url = `/api/lore/preview?tag=${encodeURIComponent(tag)}&max_chars=0`;
  const res = await apiJson(url, "GET", null);
  previewCache[tag] = (res && res.preview) ? res.preview : "";
  logDebug(`Loaded preview tag=${tag} len=${previewCache[tag].length}`);
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
  if (Object.prototype.hasOwnProperty.call(previewCache, tag)) {
    dialogText.value = previewCache[tag];
  } else {
    dialogText.value = "预览加载中...";
    await loadPreview(tag).catch(() => {});
    dialogText.value = previewCache[tag] || "";
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
  try {
    const payload = {
      mode: form.mode,
      user_task: form.userTask,
      insert_after_id: form.insertMode === "anchors" ? (form.insertAfterId || null) : null,
      insert_before_id: form.insertMode === "anchors" ? (form.insertBeforeId || null) : null,
      time_slot_override: form.insertMode === "time" ? (form.timeSlotOverride || null) : null,
      pov_character_id_override: form.povCharacterOverride || null,
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
        const extra =
          name === "writing" && evt.data?.chapter_index ? ` chapter=${evt.data.chapter_index}` : "";
        const out =
          name === "outputs_written" && evt.data?.path ? ` path=${evt.data.path}` : "";
        logText += `\n[phase] ${name}${extra}${out}\n`;
        resultText.value = `${logText}\n\n[content]\n${accContent}`;
      } else if (evt.event === "content") {
        const delta = evt.data?.delta || "";
        accContent += delta;
        // 实时刷新正文，同时保留日志
        resultText.value = `${logText}\n\n[content]\n${accContent}`;
      } else if (evt.event === "error") {
        const msg = evt.data?.message || JSON.stringify(evt.data);
        logText += `\n[error]\n${msg}\n`;
        resultText.value = `${logText}\n\n[content]\n${accContent}`;
      } else if (evt.event === "done") {
        donePayload = evt.data;
      }
    });

    if (donePayload) {
      // 不要用结构化结果覆盖掉正文；只追加一段“完成摘要”
      const ms = Date.now() - startAt;
      const ch = donePayload.chapter_index ? `chapter_index=${donePayload.chapter_index}` : "chapter_index=(auto)";
      const st = donePayload.state_updated ? "state_updated=true" : "state_updated=false";
      logText += `\n[done] ${ch}, ${st}, elapsed_ms=${ms}\n`;
      resultText.value = `${logText}\n\n[content]\n${accContent}`;
    }
    await loadAnchors();
  } finally {
    running.value = false;
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
  }
);

watch([rightTab, graphView, () => form.novelId], async ([tab]) => {
  if (tab !== "graph") return;
  await nextTick();
  // 切换视图/小说时，必须重新拉取对应 view 的数据
  await loadGraph();
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", onResize);
  if (graphChart) {
    graphChart.dispose();
    graphChart = null;
  }
});
</script>

<style scoped>
.wrap {
  max-width: 1120px;
  margin: 0 auto;
}
.header {
  margin-top: 0;
  margin-bottom: 14px;
}
.muted {
  color: #909399;
  font-size: 12px;
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

