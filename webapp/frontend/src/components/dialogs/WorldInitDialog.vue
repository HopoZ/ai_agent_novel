<script setup lang="ts">
import { ElMessageBox } from "element-plus";
import { nextTick, ref, watch } from "vue";

const visible = defineModel<boolean>({ default: false });

const props = defineProps<{
  running: boolean;
  phaseLabel: string;
  hint: string;
  streamText: string;
  tokenUsage: string;
  errorMessage: string;
}>();

const emit = defineEmits<{ abort: [] }>();

/** 距底部小于此值（px）视为「在底部」，流式更新时自动跟随 */
const STICKY_BOTTOM_PX = 72;

const scrollbarRef = ref<{
  wrapRef?: HTMLElement;
  setScrollTop?: (n: number) => void;
} | null>(null);

/** 用户未上滚时保持 true；上滚阅读时 false，回到底部后再 true */
const stickToBottom = ref(true);

function distanceFromBottom(): number {
  const wrap = scrollbarRef.value?.wrapRef;
  if (!wrap) return 0;
  return wrap.scrollHeight - wrap.scrollTop - wrap.clientHeight;
}

function onScrollbarScroll() {
  stickToBottom.value = distanceFromBottom() <= STICKY_BOTTOM_PX;
}

function scrollStreamToBottom() {
  const inst = scrollbarRef.value;
  const wrap = inst?.wrapRef;
  if (!wrap) return;
  const top = Math.max(0, wrap.scrollHeight - wrap.clientHeight);
  if (typeof inst?.setScrollTop === "function") {
    inst.setScrollTop(top);
  } else {
    wrap.scrollTop = top;
  }
}

watch(
  () => props.streamText,
  async () => {
    if (!stickToBottom.value) return;
    await nextTick();
    scrollStreamToBottom();
  },
  { flush: "post" }
);

watch(visible, (v) => {
  if (v) {
    stickToBottom.value = true;
    void nextTick(() => scrollStreamToBottom());
  }
});

function handleBeforeClose(done: () => void) {
  if (props.running) {
    ElMessageBox.confirm("生成仍在进行。关闭窗口不会自动中止；需要停止请点击「中止生成」。确定关闭？", "关闭初始化窗口", {
      confirmButtonText: "关闭窗口",
      cancelButtonText: "取消",
      type: "warning",
    })
      .then(() => done())
      .catch(() => {});
  } else {
    done();
  }
}

function closeFooter() {
  handleBeforeClose(() => {
    visible.value = false;
  });
}
</script>

<template>
  <el-dialog
    v-model="visible"
    title="本书世界观初始化"
    width="min(760px, 94vw)"
    class="world-init-dialog"
    :close-on-click-modal="false"
    :before-close="handleBeforeClose"
  >
    <p class="muted">
      模型将生成长篇 <code>NovelState</code> JSON（含人物、连续性、时间线等）。流式输出见下方；完成后写入本书
      <code>novel.db</code>。世界观原文仍以左侧 lores 为准。
    </p>
    <div class="status-row">
      <span class="phase-pill">{{ phaseLabel }}</span>
      <span class="hint">{{ hint }}</span>
    </div>
    <el-alert v-if="errorMessage" type="error" :closable="false" show-icon class="err-alert">
      {{ errorMessage }}
    </el-alert>
    <el-scrollbar
      ref="scrollbarRef"
      max-height="420px"
      @scroll="onScrollbarScroll"
    >
      <pre class="stream-pre">{{ streamText || "（等待输出…）" }}</pre>
    </el-scrollbar>
    <div v-if="tokenUsage" class="usage">{{ tokenUsage }}</div>
    <template #footer>
      <span class="dialog-footer">
        <el-button type="danger" plain :disabled="!props.running" @click="emit('abort')">中止生成</el-button>
        <el-button type="primary" @click="closeFooter">关闭</el-button>
      </span>
    </template>
  </el-dialog>
</template>

<style scoped>
.muted {
  color: var(--lit-text-2, #606266);
  font-size: 13px;
  line-height: 1.55;
  margin: 0 0 12px;
}
.muted code {
  font-size: 12px;
  background: rgba(118, 188, 255, 0.2);
  padding: 1px 6px;
  border-radius: 4px;
}
.status-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.phase-pill {
  font-size: 12px;
  font-weight: 600;
  color: #dff2ff;
  background: linear-gradient(180deg, rgba(53, 115, 203, 0.4), rgba(31, 83, 156, 0.45));
  border: 1px solid rgba(124, 187, 255, 0.7);
  padding: 4px 10px;
  border-radius: 999px;
}
.hint {
  font-size: 13px;
  color: var(--lit-text-2, #606266);
}
.err-alert {
  margin-bottom: 10px;
}
.stream-pre {
  margin: 0;
  padding: 12px;
  background: linear-gradient(180deg, rgba(12, 21, 38, 0.95), rgba(9, 16, 30, 0.95));
  border: 1px solid rgba(111, 146, 214, 0.42);
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.usage {
  margin-top: 10px;
  font-size: 12px;
  color: var(--lit-muted, #909399);
}
.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}
</style>
