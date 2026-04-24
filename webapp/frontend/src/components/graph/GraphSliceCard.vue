<template>
  <el-card class="graph-slice-card" shadow="never">
    <div class="graph-slice-head">
      <div class="graph-slice-title">图谱切片</div>
      <div class="graph-slice-actions">
        <el-button size="small" text :loading="graphLoading" @click="reloadGraph" :disabled="!novelId">
          刷新
        </el-button>
        <el-button size="small" text type="primary" @click="openGraphDialog" :disabled="!novelId">
          工作室
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
}
.graph-slice-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
}
.graph-slice-title {
  font-size: 13px;
  font-weight: 600;
}
.graph-slice-actions {
  display: flex;
  gap: 4px;
}
.graph-slice-stats-inline {
  margin-top: 4px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 12px;
  color: #606266;
}
.graph-slice-meta {
  margin-top: 4px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 12px;
  color: #909399;
}
</style>
