<template>
  <el-card class="right-panel" shadow="never">
    <div class="panel-title-row">
      <div class="panel-title">运行结果</div>
      <div class="muted">会自动显示 state.continuity / content / plan 等</div>
    </div>
    <div class="status-row">
      <el-tag size="small" :type="running ? 'warning' : (runPhase === 'error' ? 'danger' : 'success')">
        {{ running ? `进行中：${runPhaseLabel}` : `状态：${runPhaseLabel}` }}
      </el-tag>
      <span class="muted" v-if="runHint">{{ runHint }}</span>
    </div>
    <div v-if="tokenUsageText" class="output-path-tip">
      本次 Token：<code>{{ tokenUsageText }}</code>
    </div>
    <div v-if="currentNovelOutputDir" class="output-path-tip">
      当前小说输出目录：<code>{{ currentNovelOutputDir }}</code>
    </div>
    <div v-if="runRequestId || lastErrorCode" class="output-path-tip">
      <span v-if="runRequestId">request_id：<code>{{ runRequestId }}</code></span>
      <span v-if="lastErrorCode" class="error-code-inline">error_code：<code>{{ lastErrorCode }}</code></span>
    </div>
    <el-alert
      v-if="autoRejudgeText"
      class="shadow-digest"
      type="info"
      :closable="false"
      title="自动重判（本章）"
      :description="autoRejudgeText"
      show-icon
    />
    <el-alert
      v-if="shadowDigestText"
      class="shadow-digest"
      type="success"
      :closable="false"
      title="影子编导 · 结构摘要"
      :description="shadowDigestText"
      show-icon
    />
    <el-alert
      v-if="consistencyAuditText"
      class="shadow-digest"
      :type="consistencyAuditSeverity === 'high' ? 'error' : 'warning'"
      :closable="false"
      title="一致性审计"
      :description="consistencyAuditText"
      show-icon
    />
    <div v-if="lastOutputPath" class="output-path-tip">
      输出文件：<code>{{ lastOutputPath }}</code>
    </div>
    <el-divider></el-divider>
    <el-tabs :model-value="rightTab" @update:model-value="onRightTabChange" class="right-tabs">
      <el-tab-pane label="文本输出" name="result">
        <pre
          ref="resultPreRef"
          class="result-pre"
          v-text="resultText || (running ? '（进行中，等待正文输出...）' : '（本次运行暂无正文输出）')"
          @scroll.passive="onResultScroll"
        ></pre>
      </el-tab-pane>
      <el-tab-pane label="下章建议" name="next">
        <pre
          ref="nextPreRef"
          class="result-pre"
          v-text="nextStatusText || (running ? '（生成中，完成后将展示下章建议）' : '（本次运行暂无下章建议）')"
          @scroll.passive="onNextScroll"
        ></pre>
        <div class="next-actions">
          <div class="muted next-hint">可编辑后直接生成下一章（先走预览）。</div>
          <el-input
            :model-value="nextChapterDraft"
            type="textarea"
            :rows="6"
            placeholder="编辑下章方向后点击“生成下一章”"
            @update:model-value="onNextChapterDraftChange"
          />
          <div class="next-submit-row">
            <el-button
              type="primary"
              :disabled="!novelId || running || !String(nextChapterDraft || '').trim()"
              :loading="previewingInput"
              @click="onGenerateNextChapter"
            >
              生成下一章
            </el-button>
          </div>
        </div>
      </el-tab-pane>
      <el-tab-pane label="规划流" name="plan">
        <pre
          ref="planPreRef"
          class="result-pre"
          v-text="planStreamText || (running ? '（进行中，等待规划流输出...）' : '（本次运行暂无规划流输出）')"
          @scroll.passive="onPlanScroll"
        ></pre>
      </el-tab-pane>
      <el-tab-pane label="图谱可视化" name="graph">
        <div class="graph-toolbar">
          <el-button size="small" type="primary" @click="openGraphDialog" :disabled="!novelId">
            打开全屏图谱
          </el-button>
        </div>
        <div class="muted graph-hint">
          {{ novelId ? `当前视图：${graphViewLabel}` : "请先选择/创建小说，再查看图谱。" }}
        </div>
      </el-tab-pane>
    </el-tabs>
  </el-card>
</template>

<script lang="ts" setup>
import { nextTick, ref, watch } from "vue";

const props = defineProps<{
  running: boolean;
  runPhase: string;
  runPhaseLabel: string;
  runHint: string;
  tokenUsageText: string;
  currentNovelOutputDir: string;
  runRequestId: string;
  lastErrorCode: string;
  autoRejudgeText: string;
  shadowDigestText: string;
  consistencyAuditText: string;
  consistencyAuditSeverity: "ok" | "warn" | "high";
  lastOutputPath: string;
  rightTab: "result" | "next" | "plan" | "graph";
  graphView: "people" | "events" | "mixed";
  resultText: string;
  nextStatusText: string;
  nextChapterDraft: string;
  planStreamText: string;
  previewingInput: boolean;
  novelId: string;
  onRightTabChange: (v: "result" | "next" | "plan" | "graph") => void;
  onNextChapterDraftChange: (v: string) => void;
  onGenerateNextChapter: () => void;
  graphViewLabel: string;
  openGraphDialog: () => void;
}>();

const STICKY_BOTTOM_PX = 72;

const resultPreRef = ref<HTMLElement | null>(null);
const nextPreRef = ref<HTMLElement | null>(null);
const planPreRef = ref<HTMLElement | null>(null);

/** 各输出区：仅在「靠近底部」时流式更新才自动滚到底，上滚阅读时不抢滚动条 */
const stickResultBottom = ref(true);
const stickNextBottom = ref(true);
const stickPlanBottom = ref(true);

function distFromBottom(el: HTMLElement): number {
  return el.scrollHeight - el.scrollTop - el.clientHeight;
}

function onResultScroll() {
  const el = resultPreRef.value;
  if (el) stickResultBottom.value = distFromBottom(el) <= STICKY_BOTTOM_PX;
}
function onNextScroll() {
  const el = nextPreRef.value;
  if (el) stickNextBottom.value = distFromBottom(el) <= STICKY_BOTTOM_PX;
}
function onPlanScroll() {
  const el = planPreRef.value;
  if (el) stickPlanBottom.value = distFromBottom(el) <= STICKY_BOTTOM_PX;
}

async function scrollResultToBottomIfSticky() {
  await nextTick();
  const el = resultPreRef.value;
  if (!el || !stickResultBottom.value) return;
  el.scrollTop = el.scrollHeight;
}
async function scrollNextToBottomIfSticky() {
  await nextTick();
  const el = nextPreRef.value;
  if (!el || !stickNextBottom.value) return;
  el.scrollTop = el.scrollHeight;
}
async function scrollPlanToBottomIfSticky() {
  await nextTick();
  const el = planPreRef.value;
  if (!el || !stickPlanBottom.value) return;
  el.scrollTop = el.scrollHeight;
}

watch(() => props.resultText, () => void scrollResultToBottomIfSticky(), { flush: "post" });
watch(() => props.nextStatusText, () => void scrollNextToBottomIfSticky(), { flush: "post" });
watch(() => props.planStreamText, () => void scrollPlanToBottomIfSticky(), { flush: "post" });

/** 切换 Tab 时默认跟随到底（方便直接看到最新块） */
watch(
  () => props.rightTab,
  (tab) => {
    void nextTick(() => {
      if (tab === "result") {
        stickResultBottom.value = true;
        const el = resultPreRef.value;
        if (el) el.scrollTop = el.scrollHeight;
      } else if (tab === "next") {
        stickNextBottom.value = true;
        const el = nextPreRef.value;
        if (el) el.scrollTop = el.scrollHeight;
      } else if (tab === "plan") {
        stickPlanBottom.value = true;
        const el = planPreRef.value;
        if (el) el.scrollTop = el.scrollHeight;
      }
    });
  }
);
</script>

<style scoped>
.right-panel {
  border: 1px solid var(--app-panel-border, rgba(126, 163, 227, 0.45));
}
.panel-title-row {
  display: flex;
  gap: 8px;
  align-items: baseline;
  flex-wrap: wrap;
}
.panel-title {
  font-weight: 700;
}
.status-row {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  margin-top: 8px;
}
.error-code-inline {
  margin-left: 8px;
}
.muted {
  color: var(--lit-muted, #909399);
  font-size: 12px;
}
.output-path-tip {
  margin-top: 6px;
  font-size: 12px;
  color: var(--lit-text-2, #606266);
  word-break: break-all;
}
.shadow-digest {
  margin-top: 8px;
}
.result-pre {
  max-height: 48vh;
  overflow: auto;
  padding: 10px;
  background: var(--app-result-bg, #fff);
  border-radius: 10px;
  border: 1px solid var(--lit-border, #ebeef5);
  color: var(--app-result-text, inherit);
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
}
.right-tabs :deep(.el-tabs__content) {
  padding-top: 6px;
}
.next-actions {
  margin-top: 10px;
}
.next-hint {
  margin-bottom: 6px;
}
.next-submit-row {
  margin-top: 8px;
}
.graph-toolbar {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.graph-hint {
  margin-top: 8px;
}
</style>

