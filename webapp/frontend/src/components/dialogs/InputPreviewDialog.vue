<script setup lang="ts">
import { computed } from "vue";

const visible = defineModel<boolean>({ default: false });
const openStages = defineModel<string[]>("openStages", { default: () => [] });

const props = defineProps<{
  inputPreviewData: Record<string, unknown> | null;
  running: boolean;
  pendingRunStarting: boolean;
  pendingRunPayload: unknown;
  structureGate: Record<string, unknown> | null;
}>();

const emit = defineEmits<{
  copyJson: [];
  confirm: [];
  confirmRisk: [];
}>();

const stages = computed(() => {
  const d = props.inputPreviewData;
  const raw = d && Array.isArray(d.stages) ? d.stages : [];
  return raw.map((s: unknown) => {
    const x = s as { name?: unknown; system?: unknown; human?: unknown };
    return {
      name: String(x?.name ?? ""),
      system: typeof x?.system === "string" ? x.system : "",
      human: typeof x?.human === "string" ? x.human : "",
    };
  });
});

function stageDisplayTitle(name: string): string {
  const m: Record<string, string> = {
    init_state: "初始化 · 世界状态",
    plan_chapter: "规划 · 章节结构",
    write_chapter_text: "写作 · 正文生成",
    optimize_suggestions: "优化 · 建议（非整章）",
  };
  return m[name] || name || "阶段";
}
</script>

<template>
  <el-dialog
    v-model="visible"
    class="input-preview-dialog"
    title="运行前预览"
    width="85%"
    destroy-on-close
  >
    <p class="input-preview-lead muted">
      以下为本次将分阶段使用的内容。确认后点击「确认并运行」。
    </p>
    <div v-if="inputPreviewData" class="input-preview-body">
      <el-descriptions :column="2" border size="small" class="input-meta-desc">
        <el-descriptions-item label="小说 ID" :span="2">
          <code class="input-code-inline">{{ (inputPreviewData as any).novel_id || "—" }}</code>
        </el-descriptions-item>
        <el-descriptions-item label="模式">
          <el-tag size="small" type="primary">{{ (inputPreviewData as any).mode || "—" }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="手动时间段">
          {{ (inputPreviewData as any).manual_time_slot ? "是" : "否" }}
        </el-descriptions-item>
      </el-descriptions>

      <section v-if="structureGate" class="structure-card-block">
        <header class="structure-card-title">
          章节结构卡（系统已自动锁定）
        </header>
        <el-alert
          :type="(structureGate as any).needs_ack ? 'warning' : 'success'"
          :closable="false"
          :title="(structureGate as any).needs_ack ? '最小结构未满足，可返回补齐或继续生成（风险）' : '最小结构已满足，将自动进入生成'"
          :description="String((structureGate as any).risk_message || '')"
          show-icon
        />
        <el-descriptions :column="1" border size="small" class="structure-card-desc">
          <el-descriptions-item label="目标">{{ ((structureGate as any).card || {}).goal || "—" }}</el-descriptions-item>
          <el-descriptions-item label="冲突">{{ ((structureGate as any).card || {}).conflict || "—" }}</el-descriptions-item>
          <el-descriptions-item label="转折">{{ ((structureGate as any).card || {}).turning_point || "—" }}</el-descriptions-item>
          <el-descriptions-item label="伏笔回收">{{ ((structureGate as any).card || {}).foreshadow_payoff || "—" }}</el-descriptions-item>
          <el-descriptions-item label="事件归属">{{ ((structureGate as any).card || {}).event_binding || "—" }}</el-descriptions-item>
        </el-descriptions>
      </section>

      <el-collapse v-model="openStages" class="input-stages-collapse">
        <el-collapse-item
          v-for="(st, idx) in stages"
          :key="`st-${idx}-${st.name}`"
          :name="String(idx)"
        >
          <template #title>
            <span class="stage-title-text">{{ stageDisplayTitle(st.name) }}</span>
          </template>
          <div class="stage-panels">
            <section class="prompt-block">
              <header class="prompt-block-label">系统</header>
              <div class="prompt-block-body">{{ st.system || "（空）" }}</div>
            </section>
            <section class="prompt-block prompt-block--human">
              <header class="prompt-block-label">用户侧</header>
              <div class="prompt-block-body">{{ st.human || "（空）" }}</div>
            </section>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>
    <div v-else class="muted">暂无预览数据，请关闭后重试。</div>
    <template #footer>
      <span class="dialog-footer input-preview-footer">
        <el-button @click="emit('copyJson')" :disabled="!inputPreviewData">复制详情</el-button>
        <el-button @click="visible = false">关闭</el-button>
        <el-button
          v-if="(structureGate as any)?.needs_ack"
          type="warning"
          :disabled="running || !pendingRunPayload"
          :loading="pendingRunStarting"
          @click="emit('confirmRisk')"
        >
          继续生成（风险）
        </el-button>
        <el-button
          type="primary"
          :disabled="running || !pendingRunPayload"
          :loading="pendingRunStarting"
          v-if="!(structureGate as any)?.needs_ack"
          @click="emit('confirm')"
        >
          确认并运行
        </el-button>
      </span>
    </template>
  </el-dialog>
</template>

<style scoped>
.muted {
  color: #909399;
  font-size: 12px;
}
.input-preview-dialog :deep(.el-dialog) {
  max-width: 960px;
}
.input-preview-lead {
  margin: 0 0 14px;
  line-height: 1.5;
  font-size: 13px;
}
.input-preview-body {
  max-height: min(68vh, 720px);
  overflow: auto;
  padding-right: 4px;
}
.input-meta-desc {
  margin-bottom: 14px;
}
.input-code-inline {
  font-size: 12px;
  word-break: break-all;
}
.input-stages-collapse {
  border: none;
}
.structure-card-block {
  margin-bottom: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.structure-card-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.structure-card-desc {
  margin-top: 4px;
}
.input-stages-collapse :deep(.el-collapse-item__header) {
  font-weight: 600;
  padding-left: 4px;
}
.input-stages-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.stage-title-text {
  font-size: 14px;
}
.stage-panels {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 4px 0 8px;
}
.prompt-block {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  overflow: hidden;
  background: var(--el-bg-color);
}
.prompt-block-label {
  display: block;
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-light);
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.prompt-block-body {
  margin: 0;
  padding: 12px 14px;
  max-height: min(32vh, 280px);
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
  font-size: 12px;
  line-height: 1.55;
  color: var(--el-text-color-primary);
}
.prompt-block--human .prompt-block-body {
  max-height: min(40vh, 360px);
}
.input-preview-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
  width: 100%;
}
</style>
