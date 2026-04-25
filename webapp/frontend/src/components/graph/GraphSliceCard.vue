<template>
  <el-card class="graph-slice-card" shadow="never">
    <div class="graph-slice-head">
      <div class="graph-slice-title">图谱切片</div>
      <div class="graph-slice-actions">
        <el-button size="small" plain class="graph-action-btn" :loading="graphLoading" @click="reloadGraph" :disabled="!novelId">
          刷新
        </el-button>
        <el-button size="small" type="primary" plain class="graph-action-btn graph-action-btn--studio" @click="openGraphDialog" :disabled="!novelId">
          图谱工作室
        </el-button>
      </div>
    </div>

    <div class="graph-slice-stats-inline">
      <span><strong>{{ nodeTotal }}</strong> 节点</span>
      <span><strong>{{ edgeTotal }}</strong> 边</span>
      <span><strong>{{ characterTotal }}</strong> 角色</span>
    </div>

    <div class="graph-slice-meta">
      <span>事件：{{ currentEventLabel || "未绑定" }}</span>
      <span>视图：{{ graphViewLabel }}</span>
    </div>
  </el-card>
</template>

<script setup lang="ts">
defineProps<{
  novelId: string;
  graphLoading: boolean;
  nodeTotal: number;
  edgeTotal: number;
  characterTotal: number;
  currentEventLabel: string;
  graphViewLabel: string;
  reloadGraph: () => void;
  openGraphDialog: () => void;
}>();
</script>

<style scoped>
.graph-slice-card {
  margin: 4px 0 8px;
  border: 1px solid var(--app-panel-border, rgba(126, 163, 227, 0.45));
}
.graph-slice-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
}
.graph-slice-title {
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.02em;
}
.graph-slice-actions {
  display: flex;
  gap: 4px;
}
.graph-action-btn {
  min-width: 56px;
}
.graph-action-btn--studio {
  font-weight: 600;
}
.graph-slice-stats-inline {
  margin-top: 4px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--lit-text-2, #606266);
}
.graph-slice-meta {
  margin-top: 4px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--lit-muted, #909399);
}
</style>
