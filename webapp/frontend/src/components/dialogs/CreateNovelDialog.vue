<script setup lang="ts">
const visible = defineModel<boolean>({ default: false });
const novelTitle = defineModel<string>("novelTitle", { default: "" });
const startTimeSlot = defineModel<string>("startTimeSlot", { default: "" });
const povCharacterId = defineModel<string>("povCharacterId", { default: "" });

defineProps<{ running: boolean }>();

const emit = defineEmits<{ create: [] }>();
</script>

<template>
  <el-dialog v-model="visible" title="创建新小说" width="560px">
    <el-form label-position="top">
      <el-form-item label="新小说名">
        <el-input v-model="novelTitle" placeholder="例如：无尽深渊纪事"></el-input>
      </el-form-item>
      <el-form-item label="起始时间段（可选）">
        <el-input v-model="startTimeSlot" placeholder="例如：第三年秋·傍晚 / 第七日清晨"></el-input>
      </el-form-item>
      <el-form-item label="起始视角角色（可选）">
        <el-input v-model="povCharacterId" placeholder="例如：主角名/角色ID（按你的设定文本）"></el-input>
      </el-form-item>
      <div class="muted" style="margin-top:6px;">
        使用左侧“设定标签”的当前勾选作为本小说 lorebook。
      </div>
    </el-form>
    <template #footer>
      <span class="dialog-footer">
        <el-button @click="visible = false" :disabled="running">取消</el-button>
        <el-button type="primary" @click="emit('create')" :loading="running">
          {{ running ? "创建中..." : "创建并切换" }}
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
</style>
