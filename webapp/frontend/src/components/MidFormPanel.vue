<template>
  <el-card class="panel" shadow="never">
    <el-form label-position="top">
      <el-collapse :model-value="midActiveSections" @update:model-value="onMidSectionsChange">
        <el-collapse-item name="basic" title="基础">
          <div class="muted" style="margin-top:4px;">
            选择后会切换当前上下文（锚点/图谱/运行都基于当前小说）。
          </div>
          <div style="height:8px;"></div>

          <el-form-item label="选择已有小说">
            <el-select
              v-model="form.novelId"
              :loading="novelsLoading"
              clearable
              placeholder="请选择已有小说（显示小说名）"
              style="width:100%;"
            >
              <el-option
                v-for="n in novels"
                :key="n.novel_id"
                :label="n.novel_title"
                :value="n.novel_id"
              />
            </el-select>
          </el-form-item>

          <el-form-item label="当前小说名（只读）">
            <el-input :model-value="currentNovelTitle" disabled></el-input>
          </el-form-item>

          <el-form-item>
            <el-button style="width:100%;" @click="openCreateDialog" :disabled="running">
              新建小说（弹窗）
            </el-button>
          </el-form-item>

        </el-collapse-item>

        <el-collapse-item name="timeline" title="时序">
          <el-form-item label="章节归属事件（二选一）">
            <el-radio-group v-model="form.eventMode" class="choice-cards">
              <el-radio-button label="existing">归属到已有事件</el-radio-button>
              <el-radio-button label="new">新建事件并归属</el-radio-button>
            </el-radio-group>
            <div class="muted" style="margin-top:6px;">
              章节必须归属一个事件：可直接选择已有事件，或新建一个事件并指定它位于哪些事件前后。
            </div>
          </el-form-item>

          <template v-if="form.eventMode === 'existing'">
            <el-form-item label="选择已有事件（时间线事件）">
              <el-select
                v-model="form.existingEventId"
                :loading="anchorsLoading"
                clearable
                placeholder="选择本章归属的已有事件"
                style="width:100%;"
              >
                <el-option
                  v-for="a in anchors.filter((x:any) => String(x?.id || '').startsWith('ev:timeline:'))"
                  :key="a.id"
                  :label="a.label"
                  :value="a.id"
                />
              </el-select>
            </el-form-item>
          </template>

          <template v-else>
            <el-form-item label="新事件时间段（time_slot）">
              <el-input v-model="form.newEventTimeSlot" placeholder="例如：战争后期·反攻前夜"></el-input>
            </el-form-item>
            <el-form-item label="新事件摘要（summary）">
              <el-input v-model="form.newEventSummary" type="textarea" :rows="3" placeholder="一句话描述该事件"></el-input>
            </el-form-item>
            <el-form-item label="放在这个事件之后（可选）">
              <el-select
                v-model="form.newEventPrevId"
                :loading="anchorsLoading"
                clearable
                placeholder="选择前置事件（prev）"
                style="width:100%;"
              >
                <el-option
                  v-for="a in anchors.filter((x:any) => String(x?.id || '').startsWith('ev:timeline:'))"
                  :key="`prev-${a.id}`"
                  :label="a.label"
                  :value="a.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="放在这个事件之前（可选）">
              <el-select
                v-model="form.newEventNextId"
                :loading="anchorsLoading"
                clearable
                placeholder="选择后置事件（next）"
                style="width:100%;"
              >
                <el-option
                  v-for="a in anchors.filter((x:any) => String(x?.id || '').startsWith('ev:timeline:'))"
                  :key="`next-${a.id}`"
                  :label="a.label"
                  :value="a.id"
                />
              </el-select>
            </el-form-item>
          </template>
          <div class="muted" style="margin-top:6px;">
            预计本章时间段：{{ inferredTimeSlotHint || "（等待选择事件）" }}
          </div>
        </el-collapse-item>

        <el-collapse-item name="roles" title="角色">
          <el-form-item label="主视角覆盖（可多选）">
            <el-select
              v-model="form.povCharacterOverride"
              multiple
              collapse-tags
              collapse-tags-tooltip
              clearable
              filterable
              allow-create
              default-first-option
              placeholder="多选表示与本章最相关的核心人物"
              style="width:100%;"
              @change="onPovChange"
            >
              <el-option v-for="cid in allCharacterOptions" :key="cid" :label="cid" :value="cid" />
            </el-select>
          </el-form-item>
          <el-form-item label="快速多选角色（配角设定）">
            <el-select
              v-model="form.focusCharacterIds"
              multiple
              collapse-tags
              collapse-tags-tooltip
              clearable
              filterable
              allow-create
              default-first-option
              placeholder="点击快速多选作为配角设定（可清空）"
              style="width:100%;"
              @change="onFocusChange"
            >
              <el-option v-for="cid in allCharacterOptions" :key="`focus-${cid}`" :label="cid" :value="cid" />
            </el-select>
          </el-form-item>
          <el-form-item label="角色标签管理（本次会话）">
            <div style="display:flex; width:100%; justify-content:space-between; align-items:center;">
              <span class="muted">当前标签数：{{ allCharacterOptions.length }}</span>
              <el-button size="small" @click="openRoleManager">打开管理面板</el-button>
            </div>
          </el-form-item>
        </el-collapse-item>

        <el-collapse-item name="advanced" title="高级">
          <el-form-item label="首次使用（未初始化世界）">
            <el-button style="width:100%;" @click="runInitWorld" :disabled="running" plain type="warning">
              初始化世界（init_state）
            </el-button>
            <div class="muted" style="margin-top:6px;">
              新建小说后若尚未生成过完整 state，请先初始化；与下方三个写作按钮独立。
            </div>
          </el-form-item>
          <el-form-item label="章节预设名（可选）">
            <el-input v-model="form.chapterPresetName" placeholder="例如：重逢夜 / 石碑共鸣 / 古墟初探"></el-input>
          </el-form-item>
          <el-divider content-position="left">模型采样</el-divider>
          <div class="muted" style="margin-bottom:8px;">
            下面三项控制<strong>大模型怎么选词、单轮最多写多长</strong>，不改动你的小说数据/图谱逻辑。
            与 <code>_init_llm</code> 一致：<strong>temperature={{ defaultLlmTemperature }}</strong>、<strong>max_tokens={{ defaultLlmMaxTokens }}</strong>；<code>top_p</code> 未在服务端写死，留空则请求里不传（由接口默认）。
            同一次运行里：<strong>init / 规划 / 正文 / 修订 / 下章建议</strong>共用当前这组值。
          </div>
          <el-form-item :label="`temperature（默认 ${defaultLlmTemperature}）`">
            <el-input-number
              v-model="form.llmTemperature"
              :min="0"
              :max="2"
              :step="0.1"
              :precision="2"
              controls-position="right"
              style="width:100%;"
            />
            <div class="muted" style="margin-top:6px;">
              <strong>随机性</strong>：越高越敢发散、文风变化大；越低越稳、重复感强。规划 JSON 宜偏低或中等，正文可按喜好略调高。
            </div>
          </el-form-item>
          <el-form-item label="top_p（可选）">
            <el-input-number
              v-model="form.llmTopP"
              :min="0"
              :max="1"
              :step="0.05"
              :precision="2"
              controls-position="right"
              style="width:100%;"
              clearable
            />
            <div class="muted" style="margin-top:6px;">
              <strong>核采样</strong>：只在概率较高的一截候选里抽样；越低越保守整齐，越高候选面越宽。与 temperature 二选一微调即可，不必两个都极端。
            </div>
          </el-form-item>
          <el-form-item :label="`max_tokens（默认 ${defaultLlmMaxTokens}）`">
            <el-input-number
              v-model="form.llmMaxTokens"
              :min="1"
              :max="200000"
              :step="256"
              controls-position="right"
              style="width:100%;"
            />
            <div class="muted" style="margin-top:6px;">
              <strong>本轮回复长度上限</strong>（token，约等于字数折算）。太小容易规划/正文被截断；太大更耗 token、更慢，且受供应商上限限制。
            </div>
          </el-form-item>
        </el-collapse-item>

        <el-collapse-item name="task" title="本章任务">
          <el-form-item label="任务 / 素材">
            <el-input
              v-model="form.userTask"
              type="textarea"
              :rows="7"
              placeholder="生成内容：本章情节与写作要求。扩写内容：粘贴待扩写的短文/梗概（将扩至约4000–5000字）。优化内容：粘贴片段或说明希望改进的方向（输出建议，不写整章）。"
            ></el-input>
          </el-form-item>
        </el-collapse-item>
      </el-collapse>

      <div class="mid-actions-sticky">
        <div class="muted" style="margin-bottom:8px;">写作（先预览 Input，确认后再流式运行）</div>
        <div style="display:flex; flex-direction:column; gap:8px; width:100%;">
          <el-button type="primary" @click="runGenerate" :disabled="running" :loading="running">
            {{ running ? "运行中..." : "生成内容" }}
          </el-button>
          <el-button type="success" plain @click="runExpand" :disabled="running">
            扩写内容
          </el-button>
          <el-button type="info" plain @click="runOptimize" :disabled="running">
            优化内容
          </el-button>
          <el-button v-if="running" type="danger" @click="abortRun">中止生成</el-button>
        </div>
      </div>
    </el-form>
  </el-card>
</template>

<script lang="ts" setup>
defineProps<{
  form: any;
  defaultLlmTemperature: number;
  defaultLlmMaxTokens: number;
  midActiveSections: string[];
  novelsLoading: boolean;
  novels: Array<{ novel_id: string; novel_title: string }>;
  currentNovelTitle: string;
  running: boolean;
  anchorsLoading: boolean;
  anchors: Array<{ id: string; label: string; type: string; time_slot: string }>;
  inferredTimeSlotHint: string;
  allCharacterOptions: string[];
  previewingInput: boolean;
  onMidSectionsChange: (v: string[]) => void;
  openCreateDialog: () => void;
  onPovChange: (v: any) => void;
  onFocusChange: (v: any) => void;
  openRoleManager: () => void;
  runGenerate: () => void;
  runExpand: () => void;
  runOptimize: () => void;
  runInitWorld: () => void;
  abortRun: () => void;
}>();
</script>

<style scoped>
.muted {
  color: #909399;
  font-size: 12px;
}
.choice-cards {
  width: 100%;
}
.choice-cards :deep(.el-radio-button__inner) {
  width: 100%;
}
:deep(.el-collapse) {
  border-top: 0;
  border-bottom: 0;
}
:deep(.el-collapse-item__header) {
  padding: 0 10px;
  border-radius: 8px;
  margin-bottom: 6px;
  border: 1px solid #bfdcff;
  background: #f3f8ff;
  color: #1d4f91;
  font-weight: 600;
  transition: all 0.18s ease;
}
:deep(.el-collapse-item__header:hover) {
  border-color: #8ec1ff;
  background: #eaf3ff;
}
:deep(.el-collapse-item__header.is-active) {
  border-color: #409eff;
  background: #ecf5ff;
  color: #1d4f91;
  box-shadow: 0 0 0 1px rgba(64, 158, 255, 0.15) inset;
}
:deep(.el-collapse-item__content) {
  padding: 4px 2px 8px;
}
.mid-actions-sticky {
  position: sticky;
  bottom: 8px;
  background: #fff;
  padding-top: 8px;
  z-index: 3;
}
</style>

