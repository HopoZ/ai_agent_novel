<script setup lang="ts">
const visible = defineModel<boolean>({ default: false });
defineProps<{ title: string; text: string }>();
</script>

<template>
  <el-dialog v-model="visible" :title="title" width="70%">
    <div class="dialog-body">
      <pre class="dialog-pre" v-text="text"></pre>
    </div>
    <template #footer>
      <span class="dialog-footer">
        <el-button @click="visible = false">关闭</el-button>
      </span>
    </template>
  </el-dialog>
</template>

<style scoped>
.dialog-body {
  max-height: 70vh;
  overflow: auto;
  background: #fff;
  padding: 10px;
  border: 1px solid #ebeef5;
  border-radius: 10px;
}
.dialog-pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
}
</style>
