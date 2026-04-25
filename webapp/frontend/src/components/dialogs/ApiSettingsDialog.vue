<template>
  <el-dialog
    v-model="visible"
    title="LLM API 设置"
    width="min(480px, 92vw)"
    destroy-on-close
    @open="onOpen"
  >
    <p class="api-help">
      密钥仅保存在本机 <code>storage/user_settings.json</code>。支持 DeepSeek 与 OpenAI 兼容接口
      （自定义 <code>base_url</code> + <code>model</code>）。
    </p>
    <el-form label-position="top" @submit.prevent>
      <el-form-item label="提供商">
        <el-select v-model="provider" class="w-full">
          <el-option label="DeepSeek（官方）" value="deepseek" />
          <el-option label="OpenAI 兼容（第三方）" value="openai_compatible" />
        </el-select>
      </el-form-item>
      <el-form-item label="API Key">
        <el-input
          v-model="draft"
          type="password"
          show-password
          placeholder="sk-..."
          clearable
          autocomplete="off"
        />
      </el-form-item>
      <template v-if="provider === 'openai_compatible'">
        <el-form-item label="Base URL">
          <el-input
            v-model="baseUrl"
            placeholder="例如：https://api.openai.com/v1（必须是 /v1 API 根路径）"
            clearable
          />
        </el-form-item>
        <el-form-item label="Model">
          <div class="row-actions-full">
            <el-select
              v-model="model"
              filterable
              allow-create
              default-first-option
              clearable
              class="grow-1"
              placeholder="可手填，或点击右侧获取模型列表"
            >
              <el-option
                v-for="m in modelOptions"
                :key="m.id"
                :label="m.label"
                :value="m.id"
              />
            </el-select>
            <el-button
              :loading="fetchingModels"
              @click="fetchModels"
            >
              获取模型
            </el-button>
          </div>
          <div class="api-hint top-6">
            <el-checkbox v-model="forceRefreshModels">强制刷新（跳过缓存）</el-checkbox>
            <span class="left-8">{{ modelCacheHint }}</span>
          </div>
          <div v-if="selectedModelCapabilities.length" class="api-hint top-4">
            能力标签：
            <el-tag
              v-for="cap in selectedModelCapabilities"
              :key="`cap-${cap}`"
              size="small"
              effect="plain"
              class="left-6"
            >
              {{ cap }}
            </el-tag>
          </div>
        </el-form-item>
      </template>
      <div class="api-hint">
        保存前将自动测试连通性（最小请求），通过后才会写入本地配置。
      </div>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button type="danger" plain :disabled="saving" @click="onClear">清除本地保存</el-button>
      <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
    </template>
  </el-dialog>
</template>

<script lang="ts" setup>
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { apiJson } from "../../api/client";

const props = defineProps<{ modelValue: boolean }>();
const emit = defineEmits<{ (e: "update:modelValue", v: boolean): void }>();

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit("update:modelValue", v),
});

const draft = ref("");
const saving = ref(false);
const provider = ref<"deepseek" | "openai_compatible">("deepseek");
const baseUrl = ref("");
const model = ref("");
const fetchingModels = ref(false);
const modelOptions = ref<Array<{ id: string; label: string }>>([]);
const modelCapabilitiesMap = ref<Record<string, string[]>>({});
const forceRefreshModels = ref(false);
const modelCacheHint = ref("");
const sessionModelCache = new Map<string, {
  base_url: string;
  used_endpoint?: string;
  count: number;
  model_items: Array<{ id: string; label: string; capabilities: string[] }>;
  cache_hit?: boolean;
}>();

const selectedModelCapabilities = computed(() => {
  const mid = String(model.value || "").trim();
  if (!mid) return [];
  return modelCapabilitiesMap.value[mid] || [];
});

watch(visible, (v) => {
  if (!v) {
    draft.value = "";
    baseUrl.value = "";
    model.value = "";
    modelOptions.value = [];
    modelCapabilitiesMap.value = {};
    modelCacheHint.value = "";
    forceRefreshModels.value = false;
  }
});

async function onOpen() {
  draft.value = "";
  try {
    const res = (await apiJson("/api/settings", "GET", null)) as {
      deepseek_api_key_source?: string;
      llm_provider?: "deepseek" | "openai_compatible";
      openai_compatible_base_url?: string;
      openai_compatible_model?: string;
    };
    provider.value = res.llm_provider || "deepseek";
    baseUrl.value = String(res.openai_compatible_base_url || "");
    model.value = String(res.openai_compatible_model || "");
  } catch {
    provider.value = "deepseek";
    baseUrl.value = "";
    model.value = "";
  }
}

async function onSave() {
  const t = (draft.value || "").trim();
  if (!t && provider.value === "deepseek") {
    ElMessage.warning("请输入 API Key 后再保存；若仅想删除本地保存，请点「清除本地保存」。");
    return;
  }
  if (provider.value === "openai_compatible") {
    if (!t || !(baseUrl.value || "").trim() || !(model.value || "").trim()) {
      ElMessage.warning("OpenAI 兼容模式请完整填写 API Key、Base URL、Model。");
      return;
    }
  }
  saving.value = true;
  try {
    await apiJson("/api/settings/test_connection", "POST", {
      provider: provider.value,
      api_key: t,
      base_url: (baseUrl.value || "").trim() || null,
      model: (model.value || "").trim() || null,
    });
    const res = (await apiJson("/api/settings/api_key", "POST", {
      provider: provider.value,
      api_key: t,
      base_url: (baseUrl.value || "").trim(),
      model: (model.value || "").trim(),
    })) as {
      ok?: boolean;
    };
    ElMessage.success("已保存");
    visible.value = false;
  } catch (e: unknown) {
    const err = e as { message?: string };
    ElMessage.error(err?.message || String(e));
  } finally {
    saving.value = false;
  }
}

async function onClear() {
  saving.value = true;
  try {
    await apiJson("/api/settings/api_key", "POST", {
      provider: provider.value,
      api_key: "",
      base_url: provider.value === "openai_compatible" ? "" : undefined,
      model: provider.value === "openai_compatible" ? "" : undefined,
    });
    draft.value = "";
    if (provider.value === "openai_compatible") {
      baseUrl.value = "";
      model.value = "";
      modelOptions.value = [];
    }
    ElMessage.success("已清除本地保存的配置");
  } catch (e: unknown) {
    const err = e as { message?: string };
    ElMessage.error(err?.message || String(e));
  } finally {
    saving.value = false;
  }
}

async function fetchModels() {
  const key = (draft.value || "").trim();
  const url = (baseUrl.value || "").trim();
  if (!key) {
    ElMessage.warning("请先填写 API Key。");
    return;
  }
  if (provider.value === "openai_compatible" && !url) {
    ElMessage.warning("请先填写 Base URL。");
    return;
  }
  const cacheKey = `${provider.value}|${url}|${key.slice(0, 8)}`;
  if (!forceRefreshModels.value) {
    const cached = sessionModelCache.get(cacheKey);
    if (cached) {
      modelOptions.value = cached.model_items.map((x) => ({ id: x.id, label: x.label }));
      modelCapabilitiesMap.value = Object.fromEntries(
        cached.model_items.map((x) => [x.id, x.capabilities || []])
      );
      if (!model.value && cached.model_items.length) {
        model.value = cached.model_items[0]!.id;
      }
      modelCacheHint.value = `已使用会话缓存（${cached.count} 个）`;
      ElMessage.success("已使用会话缓存模型列表。");
      return;
    }
  }
  fetchingModels.value = true;
  try {
    const res = (await apiJson("/api/settings/models", "POST", {
      provider: provider.value,
      api_key: key,
      base_url: url || null,
      force_refresh: forceRefreshModels.value,
    })) as {
      base_url?: string;
      used_endpoint?: string;
      models?: string[];
      model_items?: Array<{ id?: string; name?: string; context_length?: number; capabilities?: string[] }>;
      count?: number;
      cache_hit?: boolean;
    };
    if (res.base_url) {
      baseUrl.value = String(res.base_url);
    }
    const richRows = Array.isArray(res.model_items) ? res.model_items : [];
    const rows = richRows
      .map((x) => {
        const id = String(x?.id || "").trim();
        if (!id) return null;
        const name = String(x?.name || "").trim();
        const ctx = typeof x?.context_length === "number" && x.context_length > 0 ? ` · ${x.context_length} ctx` : "";
        const caps = Array.isArray(x?.capabilities)
          ? x.capabilities.map((c) => String(c || "").trim()).filter(Boolean)
          : [];
        const capText = caps.length ? ` · [${caps.join("/")}]` : "";
        return {
          id,
          label: `${id}${name && name !== id ? ` (${name})` : ""}${ctx}${capText}`,
          capabilities: caps,
        };
      })
      .filter((x): x is { id: string; label: string; capabilities: string[] } => Boolean(x));
    modelOptions.value = rows.length
      ? rows.map((x) => ({ id: x.id, label: x.label }))
      : (Array.isArray(res.models) ? res.models : [])
          .map((x) => String(x || "").trim())
          .filter(Boolean)
          .map((id) => ({ id, label: id }));
    modelCapabilitiesMap.value = Object.fromEntries(rows.map((x) => [x.id, x.capabilities || []]));
    if (!model.value && rows.length) {
      model.value = rows[0].id;
    }
    sessionModelCache.set(cacheKey, {
      base_url: String(res.base_url || ""),
      used_endpoint: String(res.used_endpoint || ""),
      count: Number(res.count ?? modelOptions.value.length),
      model_items: rows,
      cache_hit: Boolean(res.cache_hit),
    });
    modelCacheHint.value = res.cache_hit
      ? "后端缓存命中（TTL）"
      : forceRefreshModels.value
        ? "已强制刷新（跳过缓存）"
        : "后端实时拉取并写入缓存";
    ElMessage.success(
      `已获取 ${res.count ?? modelOptions.value.length} 个模型${res.used_endpoint ? `（${res.used_endpoint}）` : ""}`
    );
  } catch (e: unknown) {
    const err = e as { message?: string };
    ElMessage.error(err?.message || String(e));
  } finally {
    fetchingModels.value = false;
  }
}
</script>

<style scoped>
.w-full {
  width: 100%;
}
.row-actions-full {
  display: flex;
  gap: 8px;
  width: 100%;
}
.grow-1 {
  flex: 1;
}
.left-8 {
  margin-left: 8px;
}
.left-6 {
  margin-left: 6px;
}
.top-6 {
  margin-top: 6px;
}
.top-4 {
  margin-top: 4px;
}
.api-help {
  margin: 0 0 12px;
  font-size: 12px;
  line-height: 1.55;
  color: var(--lit-muted, #606266);
}
.api-help code {
  font-size: 11px;
  word-break: break-all;
}
.api-hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--lit-muted, #606266);
}
</style>
