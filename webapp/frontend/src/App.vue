<template>
  <div class="wrap">
    <h2 class="header">AI 小说创作代理（稳定写小说）</h2>

    <div class="main-layout">
      <!-- 左：设定标签 -->
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

      <!-- 中：填写字段 -->
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
          :run-mode="runMode"
          :abort-run="abortRun"
        />
      </div>

      <div class="resize-handle" @mousedown="startResizeMid" title="拖动调整中间栏宽度"></div>

      <!-- 右：输出 -->
      <div class="right-pane">
        <RightPanel
          :running="running"
          :run-phase="runPhase"
          :run-phase-label="runPhaseLabel"
          :run-hint="runHint"
          :token-usage-text="tokenUsageText"
          :last-output-path="lastOutputPath"
          :right-tab="rightTab"
          :graph-view="graphView"
          :graph-view-label="graphViewLabel"
          :open-graph-dialog="openGraphDialog"
          :on-right-tab-change="onRightTabChange"
          :result-text="resultText"
          :next-status-text="nextStatusText"
          :plan-stream-text="planStreamText"
          :novel-id="form.novelId"
        />
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
        <el-button
          type="primary"
          :disabled="running || !pendingRunPayload"
          :loading="pendingRunStarting"
          @click="confirmRunFromPreview"
        >
          确认并运行
        </el-button>
        <el-button @click="inputPreviewVisible = false">关闭</el-button>
      </span>
    </template>
  </el-dialog>

  <el-dialog v-model="graphFullscreenVisible" title="图谱可视化（全屏）" fullscreen append-to-body>
    <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
      <el-button size="small" type="warning" class="back-btn-highlight" @click="closeGraphDialog">返回</el-button>
      <el-segmented
        :model-value="graphView"
        @update:model-value="onGraphViewChange"
        :options="[
          { label: '人物关系网', value: 'people' },
          { label: '剧情事件网', value: 'events' },
          { label: '混合网', value: 'mixed' },
        ]"
      />
      <el-button size="small" :loading="graphLoading" @click="loadGraph">刷新图谱</el-button>
      <span class="muted">点击节点可查看详情，滚轮可缩放，拖拽可平移。</span>
    </div>
    <div style="height:10px;"></div>
    <div class="graph-box-fullscreen">
      <div v-if="!form.novelId" style="color:#909399;">请先选择/创建小说，再查看图谱。</div>
      <div v-else :ref="onGraphRef" class="graph-canvas-fullscreen"></div>
    </div>
  </el-dialog>

  <el-drawer v-model="graphEditVisible" title="图谱编辑" size="520px" append-to-body>
    <div v-if="!graphEditNode && !graphEditEdge" class="muted">请先在图谱中点击一个节点或一条边。</div>
    <template v-else-if="graphEditEdge">
      <div class="muted">边：<code>{{ graphEditEdge.source }}</code> -> <code>{{ graphEditEdge.target }}</code></div>
      <div class="muted" style="margin-top:4px;">类型：{{ graphEditEdge.type || "relationship" }}</div>
      <div style="height:10px;"></div>
      <template v-if="String(graphEditEdge.type || '').toLowerCase() === 'relationship'">
        <el-form label-position="top">
          <el-form-item label="source">
            <el-select v-model="edgeSourceDraft" filterable placeholder="选择 source">
              <el-option v-for="c in graphCharacterNodeIds" :key="`es-${c}`" :label="c" :value="`char:${c}`" />
            </el-select>
          </el-form-item>
          <el-form-item label="target">
            <el-select v-model="edgeTargetDraft" filterable placeholder="选择 target">
              <el-option v-for="c in graphCharacterNodeIds" :key="`et-${c}`" :label="c" :value="`char:${c}`" />
            </el-select>
          </el-form-item>
          <el-form-item label="怎么关联（label）">
            <el-input v-model="edgeRelLabel" placeholder="例如：师徒 / 敌对 / 欠人情 / 互相利用" />
          </el-form-item>
          <div style="display:flex; gap:8px;">
            <el-button type="primary" @click="saveEdgeRelationship">保存边关系</el-button>
            <el-button type="danger" plain @click="deleteEdgeRelationship">删除这条边</el-button>
          </div>
        </el-form>
      </template>
      <template v-else-if="String(graphEditEdge.type || '').toLowerCase() === 'appear'">
        <el-form label-position="top">
          <el-form-item label="source（角色）">
            <el-select v-model="edgeSourceDraft" filterable placeholder="选择角色">
              <el-option v-for="c in graphCharacterNodeIds" :key="`as-${c}`" :label="c" :value="`char:${c}`" />
            </el-select>
          </el-form-item>
          <el-form-item label="target（章节事件）">
            <el-select v-model="edgeTargetDraft" filterable placeholder="选择章节事件">
              <el-option v-for="c in graphChapterNodeIds" :key="`at-${c}`" :label="c" :value="c" />
            </el-select>
          </el-form-item>
          <el-form-item label="出场/角色定位（label）">
            <el-input v-model="edgeRelLabel" placeholder="例如：出场 / 指挥 / 旁观 / 受伤撤离" />
          </el-form-item>
          <div style="display:flex; gap:8px;">
            <el-button type="primary" @click="saveEdgeRelationship">保存边</el-button>
            <el-button type="danger" plain @click="deleteEdgeRelationship">删除这条边</el-button>
          </div>
        </el-form>
      </template>
      <template v-else-if="String(graphEditEdge.type || '').toLowerCase() === 'timeline_next'">
        <el-form label-position="top">
          <el-form-item label="source（时间线事件）">
            <el-select v-model="edgeSourceDraft" filterable placeholder="选择 source">
              <el-option label="（未安排）当前时间线暂无起始事件" value="" />
              <el-option v-for="t in graphTimelineOptions" :key="`ts-${t.id}`" :label="t.label" :value="t.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="target（下一跳）">
            <el-select v-model="edgeTargetDraft" filterable placeholder="选择 target">
              <el-option label="（未安排）当前时间线暂无下个事件" value="" />
              <el-option v-for="t in graphTimelineOptions" :key="`tt-${t.id}`" :label="t.label" :value="t.id" />
            </el-select>
          </el-form-item>
          <div style="display:flex; gap:8px;">
            <el-button type="primary" @click="saveEdgeRelationship">保存边</el-button>
            <el-button type="danger" plain @click="deleteEdgeRelationship">删除当前边</el-button>
          </div>
          <div class="muted" style="margin-top:8px;">提示：timeline_next 现在直接写入“事件关系表”；手工编辑的连线会保留，未定义下跳才会自动补默认顺序边。</div>
        </el-form>
      </template>
      <template v-else-if="String(graphEditEdge.type || '').toLowerCase() === 'chapter_belongs'">
        <el-form label-position="top">
          <el-form-item label="source（章节事件）">
            <el-select v-model="edgeSourceDraft" filterable placeholder="选择章节事件">
              <el-option v-for="c in graphChapterNodeIds" :key="`cb-s-${c}`" :label="c" :value="c" />
            </el-select>
          </el-form-item>
          <el-form-item label="target（归属的时间线事件）">
            <el-select v-model="edgeTargetDraft" filterable clearable placeholder="选择时间线事件（可清空表示取消归属）">
              <el-option label="（取消归属）" value="" />
              <el-option v-for="t in graphTimelineOptions" :key="`cb-t-${t.id}`" :label="t.label" :value="t.id" />
            </el-select>
          </el-form-item>
          <div style="display:flex; gap:8px;">
            <el-button type="primary" @click="saveEdgeRelationship">保存归属</el-button>
            <el-button type="danger" plain @click="deleteEdgeRelationship">删除当前边</el-button>
          </div>
          <div class="muted" style="margin-top:8px;">提示：章节归属会写回时间线事件的 chapter_index，并同步三表。</div>
        </el-form>
      </template>
      <template v-else>
        <div class="muted">该类型边暂不支持修改（可修改 relationship 边）。</div>
      </template>
    </template>
    <template v-else>
      <div class="muted">节点：<code>{{ graphEditNode.id }}</code>（{{ graphEditNode.type }}）</div>
      <div style="height:10px;"></div>

      <template v-if="graphEditNode.type === 'character'">
        <el-form label-position="top">
          <el-form-item label="description">
            <el-input v-model="graphCharDesc" type="textarea" :rows="3" />
          </el-form-item>
          <el-form-item label="current_location">
            <el-input v-model="graphCharLoc" />
          </el-form-item>
          <el-form-item label="goals（每行一条）">
            <el-input v-model="graphCharGoals" type="textarea" :rows="4" />
          </el-form-item>
          <el-form-item label="known_facts（每行一条）">
            <el-input v-model="graphCharFacts" type="textarea" :rows="4" />
          </el-form-item>
          <el-button type="primary" @click="saveGraphNodePatch" :disabled="!form.novelId">保存节点</el-button>
        </el-form>

        <el-divider />
        <div style="font-weight:600; margin-bottom:6px;">人物关系（relationship）</div>
        <div class="muted" style="margin-bottom:10px;">修改 source 角色 -> target 角色 的关系描述。</div>
        <el-form label-position="top">
          <el-form-item label="关联到哪个角色（target）">
            <el-select v-model="relTarget" filterable clearable placeholder="选择一个角色">
              <el-option v-for="c in graphCharacterNodeIds" :key="c" :label="c" :value="c" />
            </el-select>
          </el-form-item>
          <el-form-item label="怎么关联（label）">
            <el-input v-model="relLabel" placeholder="例如：师徒 / 敌对 / 欠人情 / 互相利用" />
          </el-form-item>
          <div style="display:flex; gap:8px;">
            <el-button type="primary" @click="setRelationship">新增/更新关系</el-button>
            <el-button type="danger" plain @click="deleteRelationship">删除关系</el-button>
          </div>
        </el-form>
      </template>

      <template v-else-if="graphEditNode.type === 'faction'">
        <el-form label-position="top">
          <el-form-item label="description">
            <el-input v-model="graphFacDesc" type="textarea" :rows="6" />
          </el-form-item>
          <el-button type="primary" @click="saveGraphNodePatch" :disabled="!form.novelId">保存节点</el-button>
        </el-form>
      </template>

      <template v-else-if="graphEditNode.type === 'timeline_event'">
        <el-form label-position="top">
          <el-form-item label="time_slot">
            <el-input v-model="graphTlSlot" />
          </el-form-item>
          <el-form-item label="summary">
            <el-input v-model="graphTlSummary" type="textarea" :rows="4" />
          </el-form-item>
          <el-form-item label="上一跳（谁指向当前事件）">
            <el-select v-model="timelinePrevDraft" filterable clearable placeholder="选择上一事件（可空）">
              <el-option label="（未安排）暂无上一事件" value="" />
              <el-option
                v-for="t in graphTimelineOptions"
                :key="`prev-${t.id}`"
                :label="t.label"
                :value="t.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="下一跳（当前事件指向谁）">
            <el-select v-model="timelineNextDraft" filterable clearable placeholder="选择下一事件（可空）">
              <el-option label="（未安排）暂无下一事件" value="" />
              <el-option
                v-for="t in graphTimelineOptions"
                :key="`next-${t.id}`"
                :label="t.label"
                :value="t.id"
              />
            </el-select>
          </el-form-item>
          <el-button @click="saveTimelineNeighbors" :disabled="!form.novelId" style="margin-right:8px;">保存上下关系</el-button>
          <el-button type="primary" @click="saveGraphNodePatch" :disabled="!form.novelId">保存节点</el-button>
        </el-form>
      </template>

      <template v-else>
        <div class="muted">该类型节点暂不支持编辑。</div>
      </template>
    </template>
  </el-drawer>

  <el-dialog v-model="roleManagerVisible" title="角色标签管理（本次会话）" width="680px">
    <el-form label-position="top">
      <el-form-item label="新增角色标签">
        <div style="display:flex; gap:8px; width:100%;">
          <el-input v-model="characterTagDraft" placeholder="输入角色标签后点“添加”"></el-input>
          <el-button @click="addCharacterTag">添加</el-button>
        </div>
      </el-form-item>
      <el-form-item label="当前可选标签">
        <div style="display:flex; gap:6px; flex-wrap:wrap;">
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
          支持新增/删除角色标签；如需“修改”，先删除旧标签再添加新标签。
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <span class="dialog-footer">
        <el-button @click="roleManagerVisible = false">关闭</el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script lang="ts" setup>
import { computed, nextTick, onMounted, onBeforeUnmount, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import * as echarts from "echarts";
import TagPanel from "./components/TagPanel.vue";
import MidFormPanel from "./components/MidFormPanel.vue";
import RightPanel from "./components/RightPanel.vue";

type Mode = "init_state" | "plan_only" | "write_chapter" | "revise_chapter";

const tagsLoading = ref(true);
const tags = ref<string[]>([]);
const tagGroups = ref<Record<string, string[]>>({});
const selectedTags = ref<string[]>([]);
const tagTreeRef = ref<any>(null);
function onTagTreeRef(el: any) {
  tagTreeRef.value = el;
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
const runPhase = ref<"idle" | "planning" | "writing" | "saving" | "outputs_written" | "done" | "error">("idle");
const runHint = ref("");
const lastOutputPath = ref("");
const tokenUsageText = ref("");
const leftPanelWidth = ref(360);
const LEFT_MIN_WIDTH = 280;
const LEFT_MAX_WIDTH = 680;
let resizingLeft = false;
let resizeStartX = 0;
let resizeStartW = 0;
const midPanelWidth = ref(420);
const MID_MIN_WIDTH = 340;
const MID_MAX_WIDTH = 760;
let resizingMid = false;
let midResizeStartX = 0;
let midResizeStartW = 0;

const rightTab = ref<"result" | "next" | "plan" | "graph">("result");
const graphView = ref<"people" | "events" | "mixed">("mixed");
const graphFullscreenVisible = ref(false);
function onRightTabChange(v: "result" | "next" | "plan" | "graph") {
  rightTab.value = v;
}
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
const graphData = ref<{ nodes: any[]; edges: any[] } | null>(null);
function onGraphRef(el: any) {
  graphEl.value = el as HTMLDivElement | null;
}

const graphEditVisible = ref(false);
const graphEditNode = ref<any>(null);
const graphEditEdge = ref<any>(null);
const graphCharDesc = ref("");
const graphCharLoc = ref("");
const graphCharGoals = ref("");
const graphCharFacts = ref("");
const graphFacDesc = ref("");
const graphTlSlot = ref("");
const graphTlSummary = ref("");
const timelinePrevDraft = ref("");
const timelineNextDraft = ref("");
const relTarget = ref("");
const relLabel = ref("");
const edgeRelLabel = ref("");
const edgeSourceDraft = ref("");
const edgeTargetDraft = ref("");

const graphCharacterNodeIds = computed(() => {
  const nodes = graphData.value?.nodes || [];
  return nodes
    .filter((n: any) => n && n.type === "character" && typeof n.id === "string" && n.id.startsWith("char:"))
    .map((n: any) => String(n.id).slice("char:".length))
    .filter(Boolean);
});

const graphTimelineNodeIds = computed(() => {
  const nodes = graphData.value?.nodes || [];
  return nodes
    .filter((n: any) => n && n.type === "timeline_event" && typeof n.id === "string" && n.id.startsWith("ev:timeline:"))
    .map((n: any) => String(n.id))
    .filter(Boolean);
});

const graphTimelineOptions = computed(() => {
  const nodes = graphData.value?.nodes || [];
  return nodes
    .filter((n: any) => n && n.type === "timeline_event" && typeof n.id === "string" && n.id.startsWith("ev:timeline:"))
    .map((n: any) => ({
      id: String(n.id),
      label: String(n.label || n.id),
    }));
});

const graphChapterNodeIds = computed(() => {
  const nodes = graphData.value?.nodes || [];
  return nodes
    .filter((n: any) => n && n.type === "chapter_event" && typeof n.id === "string" && n.id.startsWith("ev:chapter:"))
    .map((n: any) => String(n.id))
    .filter(Boolean);
});

function openGraphEditor(node: any) {
  graphEditEdge.value = null;
  graphEditNode.value = node;
  graphEditVisible.value = true;
  const data = node?.data || {};
  if (node?.type === "character") {
    graphCharDesc.value = String(data?.description || "");
    graphCharLoc.value = String(data?.current_location || "");
    graphCharGoals.value = Array.isArray(data?.goals) ? data.goals.join("\n") : String(data?.goals || "");
    graphCharFacts.value = Array.isArray(data?.known_facts) ? data.known_facts.join("\n") : String(data?.known_facts || "");
  } else if (node?.type === "faction") {
    graphFacDesc.value = String(data?.description || "");
  } else if (node?.type === "timeline_event") {
    graphTlSlot.value = String(data?.time_slot || "");
    graphTlSummary.value = String(data?.summary || "");
    const edges = (graphData.value?.edges || []).filter((e: any) => (e?.type || "") === "timeline_next");
    const nodeId = String(node?.id || "");
    const incoming = edges.find((e: any) => String(e?.target || "") === nodeId);
    const outgoing = edges.find((e: any) => String(e?.source || "") === nodeId);
    timelinePrevDraft.value = String(incoming?.source || "");
    timelineNextDraft.value = String(outgoing?.target || "");
  }
  relTarget.value = "";
  relLabel.value = "";
}

async function saveTimelineNeighbors() {
  const novelId = (form.novelId || "").trim();
  const node = graphEditNode.value;
  if (!novelId || !node || node.type !== "timeline_event") return;
  const nodeId = String(node.id || "");
  if (!nodeId.startsWith("ev:timeline:")) {
    ElMessage.error("当前节点不是可编辑的时间线事件。");
    return;
  }
  if (timelinePrevDraft.value && timelinePrevDraft.value === nodeId) {
    ElMessage.error("上一跳不能指向自己。");
    return;
  }
  if (timelineNextDraft.value && timelineNextDraft.value === nodeId) {
    ElMessage.error("下一跳不能指向自己。");
    return;
  }

  const newPrev = (timelinePrevDraft.value || "").trim();
  const newNext = (timelineNextDraft.value || "").trim();
  await apiJson(`/api/novels/${encodeURIComponent(novelId)}/graph/timeline-neighbors`, "PATCH", {
    node_id: nodeId,
    prev_source: newPrev || "",
    next_target: newNext || "",
  });

  ElMessage.success("已保存事件节点的上/下关系");
  await loadGraph();
}

function openGraphEdgeEditor(edge: any) {
  graphEditNode.value = null;
  graphEditEdge.value = edge;
  graphEditVisible.value = true;
  edgeRelLabel.value = String(edge?.rel_label || (typeof edge?.label === "string" ? edge.label : ""));
  edgeSourceDraft.value = String(edge?.source || "");
  edgeTargetDraft.value = String(edge?.target || "");
}

async function saveGraphNodePatch() {
  const novelId = (form.novelId || "").trim();
  if (!novelId || !graphEditNode.value) return;
  const node = graphEditNode.value;
  let patch: any = {};
  if (node.type === "character") {
    patch = {
      description: graphCharDesc.value,
      current_location: graphCharLoc.value,
      goals: graphCharGoals.value,
      known_facts: graphCharFacts.value,
    };
  } else if (node.type === "faction") {
    patch = { description: graphFacDesc.value };
  } else if (node.type === "timeline_event") {
    patch = { time_slot: graphTlSlot.value, summary: graphTlSummary.value };
  } else {
    ElMessage.warning("该节点类型暂不支持保存。");
    return;
  }
  await apiJson(`/api/novels/${encodeURIComponent(novelId)}/graph/node`, "PATCH", {
    node_id: node.id,
    patch,
  });
  ElMessage.success("已保存节点修改");
  await loadGraph();
}

async function setRelationship() {
  const novelId = (form.novelId || "").trim();
  const node = graphEditNode.value;
  if (!novelId || !node || node.type !== "character") return;
  const srcId = String(node.id || "");
  const tgtId = (relTarget.value || "").trim();
  const label = (relLabel.value || "").trim();
  if (!tgtId || !label) {
    ElMessage.error("请选择 target 并填写关系 label。");
    return;
  }
  await apiJson(`/api/novels/${encodeURIComponent(novelId)}/graph/relationship`, "POST", {
    source: srcId,
    target: `char:${tgtId}`,
    label,
    op: "set",
  });
  ElMessage.success("已更新关系");
  await loadGraph();
}

async function deleteRelationship() {
  const novelId = (form.novelId || "").trim();
  const node = graphEditNode.value;
  if (!novelId || !node || node.type !== "character") return;
  const srcId = String(node.id || "");
  const tgtId = (relTarget.value || "").trim();
  if (!tgtId) {
    ElMessage.error("请选择要删除的 target。");
    return;
  }
  await apiJson(`/api/novels/${encodeURIComponent(novelId)}/graph/relationship`, "POST", {
    source: srcId,
    target: `char:${tgtId}`,
    label: "",
    op: "delete",
  });
  ElMessage.success("已删除关系");
  await loadGraph();
}

async function saveEdgeRelationship() {
  const novelId = (form.novelId || "").trim();
  const e = graphEditEdge.value;
  if (!novelId || !e) return;
  const source = String(e.source || "");
  const target = String(e.target || "");
  const new_source = (edgeSourceDraft.value || source).trim();
  const new_target = (edgeTargetDraft.value || target).trim();
  const label = (edgeRelLabel.value || "").trim();
  const edge_type = String(e.type || "relationship");
  if (edge_type.toLowerCase() === "relationship" && !label) {
    ElMessage.error("请先填写关系 label。");
    return;
  }
  await apiJson(`/api/novels/${encodeURIComponent(novelId)}/graph/edge`, "PATCH", {
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
  const novelId = (form.novelId || "").trim();
  const e = graphEditEdge.value;
  if (!novelId || !e) return;
  const source = String(e.source || "");
  const target = String(e.target || "");
  const edge_type = String(e.type || "relationship");
  await apiJson(`/api/novels/${encodeURIComponent(novelId)}/graph/edge`, "PATCH", {
    edge_type,
    source,
    target,
    op: "delete",
  });
  ElMessage.success("已删除边");
  await loadGraph();
}
async function openGraphDialog() {
  const novelId = (form.novelId || "").trim();
  if (!novelId) {
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
const inputPreviewText = ref("");
const pendingRunPayload = ref<any | null>(null);
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

/** 与 agents/novel_agent._init_llm 保持一致（勿与后端漂移） */
const DEFAULT_LLM_TEMPERATURE = 0.7;
const DEFAULT_LLM_MAX_TOKENS = 20000;

const form = reactive<{
  novelId: string;
  mode: Mode;
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
  mode: "write_chapter",
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

function onMidResizeMove(e: MouseEvent) {
  if (!resizingMid) return;
  const delta = e.clientX - midResizeStartX;
  const next = Math.max(MID_MIN_WIDTH, Math.min(MID_MAX_WIDTH, midResizeStartW + delta));
  midPanelWidth.value = next;
}

function onMidResizeUp() {
  if (!resizingMid) return;
  resizingMid = false;
  window.removeEventListener("mousemove", onMidResizeMove);
  window.removeEventListener("mouseup", onMidResizeUp);
}

function startResizeMid(e: MouseEvent) {
  resizingMid = true;
  midResizeStartX = e.clientX;
  midResizeStartW = midPanelWidth.value;
  window.addEventListener("mousemove", onMidResizeMove);
  window.addEventListener("mouseup", onMidResizeUp);
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

async function apiSse(
  url: string,
  method: string,
  body: any,
  onEvent: (evt: { event: string; data: any }) => void,
  signal?: AbortSignal
) {
  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
    signal,
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
  form.existingEventId = "";
  form.newEventTimeSlot = "";
  form.newEventSummary = "";
  form.newEventPrevId = "";
  form.newEventNextId = "";
  form.eventMode = "existing";
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

function buildRunPayload() {
  const novelId = (form.novelId || "").trim();
  if (!novelId) {
    ElMessage.error("请先创建新小说或填写小说编号。");
    return null;
  }

  // 不再强制要求手动 init_state：后端会在需要时自动初始化

  const loreTags = selectedTags.value || [];
  if (loreTags.length === 0) {
    ElMessage.error("请至少勾选 1 项设定（settings/*.md 文件名）。");
    return null;
  }
  if (!form.userTask || !form.userTask.trim()) {
    ElMessage.error("请输入本章任务描述（例如：写第3章 + 更新世界线/人物关系的要求）。");
    return null;
  }
  if (!validateTimePlan()) {
    return null;
  }

  const mergedTask = (() => {
    const base = form.userTask || "";
    const picked = (form.focusCharacterIds || []).filter(Boolean);
    if (picked.length === 0) return base;
    return `${base}\n\n（配角设定：${picked.join("、")}）`;
  })();
  const payload: Record<string, unknown> = {
    mode: form.mode,
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

async function executeRun(novelId: string, payload: any) {

  running.value = true;
  runAbortController = new AbortController();
  runPhase.value = "planning";
  runHint.value = "已提交任务，正在排队/规划...";
  lastOutputPath.value = "";
  tokenUsageText.value = "";
  nextStatusText.value = "";
  planStreamText.value = "";
  try {
    // 流式输出：边生成边显示
    const startAt = Date.now();
    let logText = "（流式输出开始）\n";
    let accContent = "";
    let donePayload: any = null;
    const refreshStreamText = () => {
      resultText.value = `${logText}\n\n[content]\n${accContent}`;
    };

    await apiSse(`/api/novels/${novelId}/run_stream`, "POST", payload, (evt) => {
      if (evt.event === "phase") {
        const name = String(evt.data?.name || "running");
        if (name === "planning" || name === "writing" || name === "saving" || name === "outputs_written") {
          runPhase.value = name;
        }
        if (name === "planning") rightTab.value = "plan";
        if (name === "writing") rightTab.value = "result";
        if (name === "next_status") rightTab.value = "next";
        const extra =
          name === "writing" && evt.data?.chapter_index ? ` chapter=${evt.data.chapter_index}` : "";
        const out =
          name === "outputs_written" && evt.data?.path ? ` path=${evt.data.path}` : "";
        if (name === "planning") runHint.value = "正在生成章节规划（beats + next_state）";
        if (name === "writing") runHint.value = "正在流式生成正文，请稍候...";
        if (name === "saving") runHint.value = "正在保存章节记录、世界状态和图谱三表";
        if (name === "next_status") runHint.value = "正在生成下章建议...";
        if (name === "next_status_done") runHint.value = "下章建议已生成";
        if (name === "next_status_failed") runHint.value = "下章建议生成失败（可重试）";
        if (name === "outputs_written") {
          lastOutputPath.value = String(evt.data?.path || "");
          runHint.value = "正文已归档到 outputs，可在本地打开查看";
        }
        if (name === "next_status_failed") {
          const msg = String(evt.data?.error || "未知错误");
          nextStatusText.value = `（下章建议生成失败）${msg}`;
          rightTab.value = "next";
        }
        logText += `\n[phase] ${name}${extra}${out}\n`;
        refreshStreamText();
      } else if (evt.event === "plan_content") {
        const delta = evt.data?.delta || "";
        rightTab.value = "plan";
        planStreamText.value += delta;
      } else if (evt.event === "content") {
        const delta = evt.data?.delta || "";
        rightTab.value = "result";
        accContent += delta;
        // 实时刷新正文，同时保留日志
        refreshStreamText();
      } else if (evt.event === "error") {
        const msg = evt.data?.message || JSON.stringify(evt.data);
        runPhase.value = "error";
        runHint.value = "执行失败，请查看下方错误日志";
        logText += `\n[error]\n${msg}\n`;
        refreshStreamText();
      } else if (evt.event === "done") {
        donePayload = evt.data;
        runPhase.value = "done";
        runHint.value = "本次任务已完成";
      }
    }, runAbortController.signal);

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
      nextStatusText.value = String(donePayload.next_status || "").trim();
      if (nextStatusText.value) {
        rightTab.value = "next";
      }
      refreshStreamText();
    }
    await loadAnchors();
    if (graphFullscreenVisible.value || rightTab.value === "graph") {
      await loadGraph();
    }
  } catch (e: any) {
    const aborted = e?.name === "AbortError";
    if (aborted) {
      runPhase.value = "idle";
      runHint.value = "已手动中止本次生成";
      resultText.value += "\n\n[abort]\n用户已手动中止本次流式生成。\n";
    } else {
      runPhase.value = "error";
      runHint.value = "执行失败，请查看错误信息";
      ElMessage.error(`运行失败：${e?.message || String(e)}`);
    }
  } finally {
    running.value = false;
    runAbortController = null;
  }
}

async function runMode() {
  const built = buildRunPayload();
  if (!built) return;
  previewingInput.value = true;
  runPhase.value = "idle";
  runHint.value = "正在生成本次 Input 预览...";
  try {
    const data = await apiJson(`/api/novels/${encodeURIComponent(built.novelId)}/preview_input`, "POST", built.payload);
    inputPreviewText.value = JSON.stringify(data, null, 2);
    pendingRunPayload.value = built.payload;
    pendingRunNovelId.value = built.novelId;
    runHint.value = "Input 已生成，请在弹窗点击“确认并运行”";
    inputPreviewVisible.value = true;
  } finally {
    previewingInput.value = false;
  }
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
    await executeRun(pendingRunNovelId.value, pendingRunPayload.value);
  } finally {
    pendingRunStarting.value = false;
  }
}

async function previewCurrentInput() {
  const built = buildRunPayload();
  if (!built) return;
  previewingInput.value = true;
  try {
    const data = await apiJson(`/api/novels/${encodeURIComponent(built.novelId)}/preview_input`, "POST", built.payload);
    inputPreviewText.value = JSON.stringify(data, null, 2);
    pendingRunPayload.value = built.payload;
    pendingRunNovelId.value = built.novelId;
    inputPreviewVisible.value = true;
  } finally {
    previewingInput.value = false;
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

function ensureGraphChart() {
  if (!graphEl.value) return;
  if (graphChart) return;
  graphChart = echarts.init(graphEl.value, undefined, { renderer: "canvas" });
  window.addEventListener("resize", onResize);
  graphChart.on("click", (params: any) => {
    if (params?.dataType === "node" && params?.data) {
      const n = params.data;
      // 节点点击：进入可编辑面板
      openGraphEditor(n);
    }
    if (params?.dataType === "edge" && params?.data) {
      // 边点击：进入边编辑面板
      openGraphEdgeEditor(params.data);
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
    rel_label: (typeof e?.label === "string" ? e.label : ""),
    lineStyle: { opacity: 0.7, width: 1.2, curveness: 0.18 },
    label: {
      show: !!(typeof e?.label === "string" ? e.label : ""),
      formatter: (typeof e?.label === "string" ? e.label : ""),
    },
  }));

  // 给“未安排上/下一跳”的时间线节点打黄色角标
  const timelineIds = new Set(
    nodes
      .map((n: any) => String(n?.id || ""))
      .filter((id: string) => id.startsWith("ev:timeline:") && !id.includes(":draft_"))
  );
  const inCnt = new Map<string, number>();
  const outCnt = new Map<string, number>();
  for (const id of timelineIds) {
    inCnt.set(id, 0);
    outCnt.set(id, 0);
  }
  for (const e of links) {
    if ((e?.type || "") !== "timeline_next") continue;
    const s = String(e?.source || "");
    const t = String(e?.target || "");
    if (outCnt.has(s)) outCnt.set(s, (outCnt.get(s) || 0) + 1);
    if (inCnt.has(t)) inCnt.set(t, (inCnt.get(t) || 0) + 1);
  }
  for (const n of nodes as any[]) {
    const id = String(n?.id || "");
    if (!timelineIds.has(id)) continue;
    const noPrev = (inCnt.get(id) || 0) === 0;
    const noNext = (outCnt.get(id) || 0) === 0;
    // 同时没有上下跳的一般是孤立点，不做“待定”提示，避免噪音
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

watch([graphView, () => form.novelId, graphFullscreenVisible], async ([, , opened]) => {
  if (!opened) return;
  await nextTick();
  // 全屏图谱打开时，切换视图/小说会重新拉取对应数据
  await loadGraph();
});

onBeforeUnmount(() => {
  onLeftResizeUp();
  onMidResizeUp();
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
  flex: 0 0 auto;
  min-width: 360px;
}
.right-pane { flex: 1 1 auto; min-width: 420px; }
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
.graph-box-fullscreen {
  height: calc(100vh - 180px);
  border: 1px solid #ebeef5;
  border-radius: 10px;
  background: #fff;
  overflow: hidden;
}
.graph-canvas-fullscreen {
  width: 100%;
  height: 100%;
}
.back-btn-highlight {
  font-weight: 600;
}
</style>

