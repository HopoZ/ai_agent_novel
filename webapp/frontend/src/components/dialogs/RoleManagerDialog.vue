<script setup lang="ts">
const visible = defineModel<boolean>({ default: false });
const characterTagDraft = defineModel<string>("characterTagDraft", { default: "" });

defineProps<{
  allCharacterOptions: string[];
}>();

const emit = defineEmits<{
  add: [];
  remove: [id: string];
}>();
</script>

<template>
  <el-dialog v-model="visible" title="角色标签管理（本次会话）" width="680px">
    <el-form label-position="top">
      <el-form-item label="新增角色标签">
        <div style="display:flex; gap:8px; width:100%;">
          <el-input v-model="characterTagDraft" placeholder="输入角色标签后点“添加”"></el-input>
          <el-button @click="emit('add')">添加</el-button>
        </div>
      </el-form-item>
      <el-form-item label="当前可选标签">
        <div style="display:flex; gap:6px; flex-wrap:wrap;">
          <el-tag
            v-for="cid in allCharacterOptions"
            :key="`mg-${cid}`"
            closable
            @close="emit('remove', cid)"
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
        <el-button @click="visible = false">关闭</el-button>
      </span>
    </template>
  </el-dialog>
</template>

<style scoped>
.muted {
  color: #909399;
  font-size: 12px;
}
</style>
