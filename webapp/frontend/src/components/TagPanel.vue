<template>
  <el-card class="panel tag-panel" shadow="never">
    <div class="panel-head">
      <div class="panel-title">设定标签</div>
      <span class="muted">可勾选 / 预览摘要</span>
    </div>

    <el-divider></el-divider>

    <div class="tag-actions">
      <el-button size="small" type="primary" plain @click="onSelectAll">全选</el-button>
      <el-button size="small" type="primary" plain @click="onInvertSelect">反选</el-button>
      <el-button size="small" type="danger" plain @click="onClearSelect">清空</el-button>
      <el-button size="small" type="primary" plain :disabled="!canSyncNovelTags" @click="onLoadNovelTags">
        从本书加载
      </el-button>
      <el-button size="small" type="success" :disabled="!canSyncNovelTags" @click="onSaveNovelTags">
        保存到本书
      </el-button>
      <el-button size="small" type="primary" plain @click="onOpenTagManager">
        管理Tags
      </el-button>
      <el-button size="small" type="primary" :loading="buildingLoreSummary" @click="onBuildCurrentLoreSummary">
        生成当前Tag摘要
      </el-button>
    </div>

    <div v-if="tagsLoading" class="muted">正在加载设定文件...</div>
    <div v-else class="tag-list-scroll">
      <el-tree
        :ref="onTagTreeRef"
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
                    plain
                    type="primary"
                    class="tag-inline-action"
                    @click.stop
                  >
                    预览摘要
                  </el-button>
                </template>
              </el-popover>
              <el-button
                size="small"
                plain
                type="primary"
                class="tag-inline-action"
                @click.stop.prevent="onOpenTagDialog(data.tag)"
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
</template>

<script lang="ts" setup>
defineProps<{
  tagsLoading: boolean;
  buildingLoreSummary: boolean;
  canSyncNovelTags: boolean;
  onTagTreeRef: (el: any) => void;
  tagTreeData: any[];
  onSelectAll: () => void;
  onInvertSelect: () => void;
  onClearSelect: () => void;
  onBuildCurrentLoreSummary: () => void;
  onLoadNovelTags: () => void;
  onSaveNovelTags: () => void;
  onOpenTagManager: () => void;
  onTreeCheck: () => void;
  getTagPreview: (tag: string) => string;
  onOpenTagDialog: (tag: string) => void;
}>();
</script>

<style scoped>
.tag-panel {
  border: 1px solid var(--app-panel-border, rgba(126, 163, 227, 0.45));
}
.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.panel-title {
  font-weight: 700;
  letter-spacing: 0.02em;
}
.tag-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.tag-inline-action {
  min-width: 72px;
}
.muted {
  color: var(--lit-muted, #909399);
  font-size: 12px;
}
.tag-list-scroll {
  max-height: 72vh;
  overflow: auto;
  padding-right: 6px;
}
.tag-tree {
  font-size: 13px;
  border: 1px solid var(--app-tag-tree-border, rgba(130, 151, 190, 0.24));
  border-radius: 10px;
  padding: 6px;
  background: var(--app-tag-tree-bg, transparent);
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
  color: var(--lit-muted, #909399);
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
</style>

