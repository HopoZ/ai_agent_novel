<script setup lang="ts">
const visible = defineModel<boolean>({ default: false });
const novelTitle = defineModel<string>("novelTitle", { default: "" });
const startTimeSlot = defineModel<string>("startTimeSlot", { default: "" });
const povCharacterId = defineModel<string>("povCharacterId", { default: "" });
const autoGenerateLore = defineModel<boolean>("autoGenerateLore", { default: true });
const autoLoreBrief = defineModel<string>("autoLoreBrief", { default: "" });

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
      <el-form-item label="自动生成设定包">
        <el-switch v-model="autoGenerateLore" />
        <div class="muted" style="margin-top:4px;">
          创建后自动在 lores 生成“世界观骨架 / 角色关系 / 主线伏笔”草案，便于直接管理与改写。
        </div>
      </el-form-item>
      <el-form-item v-if="autoGenerateLore" label="自动设定补充说明（可选）">
        <el-input
          v-model="autoLoreBrief"
          type="textarea"
          :rows="3"
          placeholder="例如：偏硬科幻、主角成长慢热、前20章埋设3条可回收伏笔"
        />
      </el-form-item>
      <div class="muted" style="margin-top:6px;">
        将使用左侧当前勾选的设定；创建完成后会自动准备好本书的世界观与状态。
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
