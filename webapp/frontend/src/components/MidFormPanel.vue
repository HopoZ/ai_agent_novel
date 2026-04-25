<template>
  <el-card class="panel mid-panel" shadow="never">
    <el-form label-position="top">
      <div class="workbench-head">
        <div class="wb-title">导演工作台</div>
        <div class="muted">手动流转：阶段完成后高亮下一步按钮</div>
      </div>
      <div class="current-stage-banner">
        <el-tag type="success" effect="dark" class="current-stage-tag">当前：{{ stageLabel }}</el-tag>
        <div class="stage-nav-row">
          <el-button
            size="small"
            class="stage-chip"
            :class="{ 'is-active': autoStage === 'timeline' }"
            :disabled="autoStage === 'timeline'"
            @click="goToStage('timeline')"
          >
            Step 1
          </el-button>
          <el-button
            size="small"
            class="stage-chip"
            :class="{ 'is-active': autoStage === 'roles' }"
            :disabled="autoStage === 'roles' || !step1ReadyForFlow()"
            @click="goToStage('roles')"
          >
            Step 2
          </el-button>
          <el-button
            size="small"
            class="stage-chip"
            :class="{ 'is-active': autoStage === 'task' }"
            :disabled="autoStage === 'task' || !step1ReadyForFlow()"
            @click="goToStage('task')"
          >
            Step 3
          </el-button>
          <el-button
            size="small"
            class="stage-chip"
            :class="{ 'is-active': autoStage === 'confirm' }"
            :disabled="autoStage === 'confirm' || !step1ReadyForFlow()"
            @click="goToStage('confirm')"
          >
            Step 4
          </el-button>
        </div>
      </div>
      <GraphSliceCard
        :novel-id="form.novelId"
        :graph-loading="graphLoading"
        :node-total="graphNodeTotal"
        :edge-total="graphEdgeTotal"
        :character-total="graphCharacterTotal"
        :current-event-label="currentEventLabel"
        :graph-view-label="graphViewLabel"
        :reload-graph="reloadGraphSlice"
        :open-graph-dialog="openGraphDialog"
      />

      <section v-show="autoStage === 'timeline'" ref="timelineRef" class="workbench-section">
        <header class="section-title">Step 1 · 时序决策</header>
          <el-form-item label="选择已有小说">
            <el-input
              v-model="novelKeyword"
              clearable
              placeholder="按小说名或ID筛选"
              class="input-gap-bottom"
            />
            <el-select
              v-model="form.novelId"
              :loading="novelsLoading"
              clearable
              placeholder="请选择已有小说（显示小说名）"
              class="w-full"
            >
              <el-option
                v-for="n in filteredNovels"
                :key="n.novel_id"
                :label="`${n.novel_title}${n.initialized ? '' : '（未初始化）'}`"
                :value="n.novel_id"
              />
            </el-select>
            <div class="muted muted-top-4">
              当前匹配 {{ filteredNovels.length }} / {{ novels.length }} 本
            </div>
          </el-form-item>
          <el-form-item label="当前小说名（只读）">
            <el-input :model-value="currentNovelTitle" disabled></el-input>
          </el-form-item>
          <el-form-item>
            <div class="row-actions-full">
              <el-button class="grow-1" type="primary" plain @click="openCreateDialog" :disabled="running">
                新建小说
              </el-button>
              <el-button class="grow-1" type="primary" plain :disabled="!form.novelId || running" @click="renameCurrentNovel">
                重命名
              </el-button>
              <el-button
                class="grow-1"
                type="danger"
                plain
                :disabled="!form.novelId || running"
                @click="deleteCurrentNovel"
              >
                删除
              </el-button>
            </div>
          </el-form-item>
          <div class="muted muted-top-4">
            写作流程只消费“已有时间线事件”。新建事件统一在图谱工作室完成。
          </div>
          <div class="gap-8"></div>
          <el-form-item label="章节归属事件（已有时间线事件）">
            <el-select
              v-model="form.existingEventId"
              :loading="anchorsLoading"
              clearable
              placeholder="选择本章归属的已有事件"
              class="w-full"
            >
              <el-option
                v-for="a in timelineEventAnchors"
                :key="a.id"
                :label="a.label"
                :value="a.id"
              />
            </el-select>
            <div class="muted muted-top-6">
              若当前没有可选事件，请先到图谱工作室新建 timeline_event，再回到此处绑定。
            </div>
            <el-button
              size="small"
              type="primary"
              plain
              class="compact-text-btn"
              @click="openGraphDialog"
            >
              去图谱工作室新建事件
            </el-button>
          </el-form-item>
          <div class="muted muted-top-6">
            预计本章时间段：{{ inferredTimeSlotHint || "（等待选择事件）" }}
          </div>
          <el-alert
            type="warning"
            :closable="false"
            class="alert-top-8"
          >
            <template #title>
              事件计划：{{ eventPlanStatusText || "未绑定事件" }}
            </template>
            <div class="muted muted-top-4">计划完整度：{{ eventPlanQualityText || "未知" }}</div>
            <el-button
              size="small"
              type="primary"
              plain
              class="compact-text-btn"
              :disabled="!step1Done() || running"
              @click="generateBoundEventPlan"
            >
              为当前事件生成/重生成计划
            </el-button>
            <el-button
              size="small"
              type="primary"
              plain
              class="compact-text-btn"
              @click="openEventPlanManager"
            >
              打开事件计划管理
            </el-button>
          </el-alert>
          <el-alert
            v-if="suggestedTimelineEventLabel"
            type="success"
            :closable="false"
            class="alert-top-8"
          >
            <template #title>
              影子编导建议：可挂载到「{{ suggestedTimelineEventLabel }}」
            </template>
            <el-button
              size="small"
              type="primary"
              link
              class="compact-text-btn"
              @click="applySuggestedTimelineEvent"
            >
              一键采用
            </el-button>
          </el-alert>
          <el-alert
            v-if="shadowDirectorAppliedSummary"
            type="info"
            :closable="false"
            class="alert-top-8"
          >
            <template #title>
              影子编导已自动接管细节：{{ shadowDirectorAppliedSummary }}
            </template>
            <el-button
              size="small"
              type="danger"
              plain
              @click="undoShadowDirectorApply"
            >
              撤销最近自动导演系统接管
            </el-button>
          </el-alert>
          <div class="section-step-actions">
            <el-button
              type="primary"
              size="small"
              :disabled="!step1ReadyForFlow()"
              :class="{ 'next-ready': step1ReadyForFlow() }"
              @click="goToStage('roles')"
            >
              下一步：角色与冲突
            </el-button>
          </div>
      </section>

      <section v-show="autoStage === 'roles'" ref="rolesRef" class="workbench-section">
        <header class="section-title">Step 2 · 角色与冲突</header>
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
              class="w-full"
              @change="onPovChangeAndArm"
            >
              <el-option
                v-for="opt in allCharacterOptions"
                :key="opt.id"
                :label="opt.label"
                :value="opt.id"
              />
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
              class="w-full"
              @change="onFocusChangeAndArm"
            >
              <el-option
                v-for="opt in allCharacterOptions"
                :key="`focus-${opt.id}`"
                :label="opt.label"
                :value="opt.id"
              />
            </el-select>
          </el-form-item>
          <el-divider content-position="left">高价值选择（最多三项）</el-divider>
          <el-form-item label="冲突类型">
            <el-segmented
              v-model="form.conflictChoice"
              :options="['自动', '动作对抗', '信息差冲突', '价值观冲突', '利益博弈冲突']"
              class="w-full"
            />
          </el-form-item>
          <el-form-item label="伏笔回收策略">
            <el-segmented
              v-model="form.foreshadowChoice"
              :options="['自动', '优先回收旧伏笔', '承接上一章尾钩', '回收时间线事件']"
              class="w-full"
            />
          </el-form-item>
          <el-form-item label="配角介入强度">
            <el-segmented
              v-model="form.supportingPreset"
              :options="['自动', '克制', '平衡', '强化']"
              class="w-full"
            />
          </el-form-item>
          <el-form-item label="角色标签管理（本次会话）">
            <div class="row-between-full">
              <span class="muted">当前标签数：{{ allCharacterOptions.length }}</span>
              <el-button size="small" @click="openRoleManager">打开管理面板</el-button>
            </div>
          </el-form-item>
          <div class="section-step-actions">
            <el-button size="small" @click="goToStage('timeline')">上一步：时序决策</el-button>
            <el-button
              type="primary"
              size="small"
              :disabled="!step2Touched()"
              :class="{ 'next-ready': step2Touched() }"
              @click="goToStage('task')"
            >
              下一步：任务与结构卡
            </el-button>
          </div>
      </section>

      <section v-show="autoStage === 'task'" ref="taskRef" class="workbench-section">
        <header class="section-title">Step 3 · 任务与结构卡</header>
          <el-form-item label="当前地图（可选）">
            <el-input
              v-model="form.currentMap"
              type="textarea"
              :rows="3"
              placeholder="例如：青石镇东市、地下遗迹二层、星舰舰桥"
            />
            <div class="muted muted-top-6">
              留空不写；填写后会与本次写作要求一并使用。
            </div>
          </el-form-item>
          <el-form-item label="任务 / 素材">
            <el-input
              v-model="form.userTask"
              type="textarea"
              :rows="7"
              placeholder="本章要写的情节与要求；或扩写用的短文；或待优化的片段，4字以上。"
              @focus="onUserTaskFocus"
              @blur="onUserTaskBlur"
            ></el-input>
            <div class="muted muted-with-actions">
              <span>为空时会自动推测任务草案，你可直接修改后确认。</span>
              <el-button size="small" plain type="primary" @click="resetAutoTaskDraft">
                重置为自动推测
              </el-button>
            </div>
          </el-form-item>
          <el-form-item label="章节预设名（可选）">
            <el-input v-model="form.chapterPresetName" placeholder="例如：重逢夜 / 石碑共鸣 / 古墟初探"></el-input>
          </el-form-item>
          <el-divider content-position="left">模型采样（可选）</el-divider>
          <div class="muted muted-bottom-8">
            调整随机性与长度。留空则用默认（temperature {{ defaultLlmTemperature }}，max_tokens {{ defaultLlmMaxTokens }}）。
          </div>
          <el-form-item :label="`temperature（默认 ${defaultLlmTemperature}）`">
            <el-input-number
              v-model="form.llmTemperature"
              :min="0"
              :max="2"
              :step="0.1"
              :precision="2"
              controls-position="right"
              class="w-full"
            />
          </el-form-item>
          <el-form-item label="top_p（可选）">
            <el-input-number
              v-model="form.llmTopP"
              :min="0"
              :max="1"
              :step="0.05"
              :precision="2"
              controls-position="right"
              class="w-full"
              clearable
            />
          </el-form-item>
          <el-form-item :label="`max_tokens（默认 ${defaultLlmMaxTokens}）`">
            <el-input-number
              v-model="form.llmMaxTokens"
              :min="1"
              :max="200000"
              :step="256"
              controls-position="right"
              class="w-full"
            />
          </el-form-item>
          <div class="section-step-actions">
            <el-button size="small" @click="goToStage('roles')">上一步：角色与冲突</el-button>
            <el-button
              type="primary"
              size="small"
              :disabled="!taskReady"
              :class="{ 'next-ready': taskReady }"
              @click="goToStage('confirm')"
            >
              下一步：预览与运行
            </el-button>
          </div>
      </section>

      <section v-show="autoStage === 'confirm'" ref="confirmRef" class="workbench-section">
        <header class="section-title">Step 4 · 预览与运行</header>
          <div class="muted muted-bottom-8">
            建议先预览后运行。需要看流式输出/审计时，打开右上角运行面板。
          </div>
          <el-button size="small" @click="openInsightsDrawer" :disabled="!form.novelId">
            打开运行面板
          </el-button>
          <div class="section-step-actions">
            <el-button size="small" @click="goToStage('task')">上一步：任务与结构卡</el-button>
          </div>
      </section>

      <div class="mid-actions-sticky">
        <div class="muted muted-bottom-8">
          写作：先预览，再运行。
        </div>
        <div class="actions-column-full">
          <el-button type="primary" @click="runGenerate" :disabled="running" :loading="running">
            {{ running ? "运行中..." : "生成内容" }}
          </el-button>
          <el-button type="success" plain @click="runExpand" :disabled="running">
            扩写内容
          </el-button>
          <el-button type="info" plain @click="runOptimize" :disabled="running">
            优化内容
          </el-button>
          <el-button v-if="running" type="danger" @click="abortRun">中止生成</el-button>
        </div>
      </div>
    </el-form>
  </el-card>
</template>

<script lang="ts" setup>
import { computed, ref, watch } from "vue";
import GraphSliceCard from "./graph/GraphSliceCard.vue";

const props = defineProps<{
  form: any;
  defaultLlmTemperature: number;
  defaultLlmMaxTokens: number;
  midActiveSection: string;
  novelsLoading: boolean;
  novels: Array<{ novel_id: string; novel_title: string; initialized?: boolean }>;
  currentNovelTitle: string;
  running: boolean;
  anchorsLoading: boolean;
  anchors: Array<{ id: string; label: string; type: string; time_slot: string }>;
  inferredTimeSlotHint: string;
  eventPlanStatusText: string;
  eventPlanReady: boolean;
  eventPlanQualityText: string;
  suggestedTimelineEventLabel: string;
  allCharacterOptions: Array<{ id: string; label: string }>;
  previewingInput: boolean;
  onMidSectionChange: (v: string | string[]) => void;
  openCreateDialog: () => void;
  renameCurrentNovel: () => void;
  deleteCurrentNovel: () => void;
  onPovChange: (v: any) => void;
  onFocusChange: (v: any) => void;
  applySuggestedTimelineEvent: () => void;
  shadowDirectorAppliedSummary: string;
  undoShadowDirectorApply: () => void;
  openRoleManager: () => void;
  runGenerate: () => void;
  runExpand: () => void;
  runOptimize: () => void;
  abortRun: () => void;
  openInsightsDrawer: () => void;
  openEventPlanManager: () => void;
  generateBoundEventPlan: () => void;
  graphLoading: boolean;
  graphNodeTotal: number;
  graphEdgeTotal: number;
  graphCharacterTotal: number;
  currentEventLabel: string;
  graphViewLabel: string;
  reloadGraphSlice: () => void;
  openGraphDialog: () => void;
}>();

const timelineRef = ref<HTMLElement | null>(null);
const rolesRef = ref<HTMLElement | null>(null);
const taskRef = ref<HTMLElement | null>(null);
const confirmRef = ref<HTMLElement | null>(null);
const autoStage = ref<"timeline" | "roles" | "task" | "confirm">("timeline");
const stageLabel = computed(() => {
  if (autoStage.value === "timeline") return "Step 1 · 时序决策";
  if (autoStage.value === "roles") return "Step 2 · 角色与冲突";
  if (autoStage.value === "task") return "Step 3 · 任务与结构卡";
  return "Step 4 · 预览与运行";
});
const taskReady = computed(() => String(props.form?.userTask || "").trim().length >= 4);
const novelKeyword = ref("");
const filteredNovels = computed(() => {
  const kw = String(novelKeyword.value || "").trim().toLowerCase();
  if (!kw) return props.novels || [];
  return (props.novels || []).filter((n) => {
    const title = String(n.novel_title || "").toLowerCase();
    const id = String(n.novel_id || "").toLowerCase();
    return title.includes(kw) || id.includes(kw);
  });
});
const timelineEventAnchors = computed(() =>
  (props.anchors || []).filter((x: any) => String(x?.id || "").startsWith("ev:timeline:"))
);

function _shortId(v: string): string {
  const s = String(v || "").trim();
  if (!s) return "";
  if (s.length <= 10) return s;
  return `${s.slice(0, 4)}...${s.slice(-4)}`;
}

function buildAutoTaskDraft(): string {
  const title = String(props.currentNovelTitle || "").trim() || "当前小说";
  const inferredSlot = String(props.inferredTimeSlotHint || "").trim();
  const slotLine = inferredSlot || "（待确认）";
  const eventHint = `绑定已有事件：${_shortId(String(props.form?.existingEventId || "").trim()) || "（待选择）"}`;
  const pov = Array.isArray(props.form?.povCharacterOverride)
    ? props.form.povCharacterOverride.filter((x: unknown) => String(x || "").trim()).join("、")
    : "";
  const supporting = Array.isArray(props.form?.focusCharacterIds)
    ? props.form.focusCharacterIds.filter((x: unknown) => String(x || "").trim()).join("、")
    : "";
  const conflict = String(props.form?.conflictChoice || "自动").trim();
  const foreshadow = String(props.form?.foreshadowChoice || "自动").trim();
  const mapText = String(props.form?.currentMap || "").trim();
  const mapLine = mapText ? `- 场景地图：${mapText}` : "- 场景地图：按当前章节上下文自动选择";

  return (
    `请为《${title}》生成下一章可直接写作的内容，保持连续性与节奏推进。\n\n` +
    `- 时间段：${slotLine}\n` +
    `- ${eventHint}\n` +
    `- 主视角（建议）：${pov || "自动"}\n` +
    `- 配角参与（建议）：${supporting || "自动"}\n` +
    `- 冲突类型：${conflict || "自动"}\n` +
    `- 伏笔策略：${foreshadow || "自动"}\n` +
    `${mapLine}\n\n` +
    "写作要求：先推进主冲突，再给一个可承接下章的收束钩子；避免与既有设定冲突。"
  );
}

function ensureAutoTaskIfEmpty() {
  const now = String(props.form?.userTask || "").trim();
  if (now) return;
  props.form.userTask = buildAutoTaskDraft();
}

function resetAutoTaskDraft() {
  props.form.userTask = buildAutoTaskDraft();
}

function scrollToSection(name: "timeline" | "roles" | "task" | "confirm") {
  const target =
    name === "timeline"
      ? timelineRef.value
      : name === "roles"
        ? rolesRef.value
        : name === "task"
          ? taskRef.value
          : confirmRef.value;
  target?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function goToStage(name: "timeline" | "roles" | "task" | "confirm") {
  if (name === "task") {
    ensureAutoTaskIfEmpty();
  }
  autoStage.value = name;
  scrollToSection(name);
}

function step1Done(): boolean {
  return Boolean(String(props.form?.existingEventId || "").trim());
}

function step1ReadyForFlow(): boolean {
  return step1Done() && Boolean(props.eventPlanReady);
}

function step2Touched(): boolean {
  const povN = Array.isArray(props.form?.povCharacterOverride) ? props.form.povCharacterOverride.length : 0;
  const focusN = Array.isArray(props.form?.focusCharacterIds) ? props.form.focusCharacterIds.length : 0;
  const conflict = String(props.form?.conflictChoice || "自动");
  const foreshadow = String(props.form?.foreshadowChoice || "自动");
  const supporting = String(props.form?.supportingPreset || "自动");
  return (
    povN > 0 ||
    focusN > 0 ||
    conflict !== "自动" ||
    foreshadow !== "自动" ||
    supporting !== "自动"
  );
}

function onPovChangeAndArm(v: any) {
  props.onPovChange(v);
}

function onFocusChangeAndArm(v: any) {
  props.onFocusChange(v);
}

function onUserTaskFocus() {
  // no-op: 保留事件签名，避免模板改动过大
}

function onUserTaskBlur() {
  // no-op: 取消自动跳转，仅保留“下一步按钮高亮”
}

watch(
  () => props.form?.novelId,
  () => {
    props.form.eventMode = "existing";
    props.form.newEventTimeSlot = "";
    props.form.newEventSummary = "";
    props.form.newEventPrevId = "";
    props.form.newEventNextId = "";
    autoStage.value = "timeline";
    scrollToSection("timeline");
  }
);

watch(
  () => props.form?.eventMode,
  (mode) => {
    if (String(mode || "").trim() !== "existing") {
      props.form.eventMode = "existing";
    }
  }
);

watch(
  () => [
    props.form?.eventMode,
    props.form?.existingEventId,
    props.form?.newEventTimeSlot,
    props.form?.newEventSummary,
    props.form?.povCharacterOverride,
    props.form?.focusCharacterIds,
    props.form?.conflictChoice,
    props.form?.foreshadowChoice,
    props.form?.supportingPreset,
    props.form?.currentMap,
    props.inferredTimeSlotHint,
    props.currentNovelTitle,
  ],
  () => {
    if (autoStage.value === "task") {
      ensureAutoTaskIfEmpty();
    }
  },
  { deep: true }
);
</script>

<style scoped>
.mid-panel {
  border: 1px solid var(--app-panel-border, rgba(126, 163, 227, 0.45));
}
.workbench-head {
  margin-bottom: 8px;
}
.wb-title {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.03em;
}
.current-stage-banner {
  margin: 6px 0 10px;
  padding: 8px 10px;
  border: 1px solid var(--app-stage-banner-border, rgba(108, 161, 234, 0.58));
  border-radius: 8px;
  background: var(--app-stage-banner-bg, linear-gradient(180deg, rgba(29, 47, 84, 0.72), rgba(18, 31, 56, 0.78)));
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: nowrap;
  overflow-x: auto;
}
.current-stage-tag {
  flex: 0 0 auto;
}
.workbench-section {
  border: 1px solid var(--app-workbench-border, rgba(111, 146, 214, 0.4));
  border-radius: 10px;
  padding: 12px;
  margin-bottom: 10px;
  background: var(--app-workbench-bg, linear-gradient(180deg, rgba(20, 32, 58, 0.72), rgba(13, 24, 45, 0.8)));
}
.section-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--app-workbench-title, #d6e9ff);
  margin-bottom: 8px;
}
.muted {
  color: var(--lit-muted, #909399);
  font-size: 12px;
}
.w-full {
  width: 100%;
}
.input-gap-bottom {
  margin-bottom: 6px;
}
.muted-top-4 {
  margin-top: 4px;
}
.muted-top-6 {
  margin-top: 6px;
}
.muted-bottom-8 {
  margin-bottom: 8px;
}
.row-actions-full {
  display: flex;
  gap: 8px;
  width: 100%;
}
.row-between-full {
  display: flex;
  width: 100%;
  justify-content: space-between;
  align-items: center;
}
.grow-1 {
  flex: 1;
}
.gap-8 {
  height: 8px;
}
.alert-top-8 {
  margin-top: 8px;
}
.compact-text-btn {
  padding: 4px 10px;
}
.muted-with-actions {
  margin-top: 6px;
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.actions-column-full {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}
.choice-cards {
  width: 100%;
}
.choice-cards :deep(.el-radio-button__inner) {
  width: 100%;
}
.section-step-actions {
  margin-top: 8px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.next-ready {
  box-shadow: 0 0 0 2px rgba(67, 213, 140, 0.24);
  border-color: #43d58c;
}
.stage-nav-row {
  display: flex;
  gap: 8px;
  flex-wrap: nowrap;
  align-items: center;
  margin: 0;
  overflow-x: auto;
  padding-bottom: 0;
}
.stage-chip {
  min-width: 78px;
  border: 1px solid var(--app-stage-chip-border, rgba(111, 146, 214, 0.45));
  background: var(--app-stage-chip-bg, linear-gradient(180deg, rgba(34, 52, 89, 0.74) 0%, rgba(24, 38, 69, 0.82) 100%));
  color: var(--app-stage-chip-text, #d4e7ff);
  letter-spacing: 0.02em;
}
.stage-chip.is-active {
  border-color: var(--app-stage-chip-active-border, #7bc4ff);
  background: var(--app-stage-chip-active-bg, linear-gradient(180deg, #48a8ff 0%, #2a85f4 100%));
  color: var(--app-stage-chip-active-text, #081628);
  box-shadow: var(--app-stage-chip-active-shadow, 0 0 0 1px rgba(191, 230, 255, 0.35) inset);
}
.mid-actions-sticky {
  position: sticky;
  bottom: 8px;
  background: var(--app-sticky-bg, linear-gradient(180deg, rgba(16, 25, 46, 0.86), rgba(12, 20, 37, 0.92)));
  border-top: 1px solid var(--app-sticky-border, rgba(111, 146, 214, 0.3));
  border-radius: 10px;
  padding: 10px;
  padding-top: 8px;
  z-index: 3;
}
</style>

