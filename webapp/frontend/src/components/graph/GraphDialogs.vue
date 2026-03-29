<script setup lang="ts">
import { inject } from "vue";
import { GRAPH_INJECTION_KEY, type GraphController } from "../../composables/useGraph";

defineProps<{ novelId: string }>();

const graph = inject(GRAPH_INJECTION_KEY) as GraphController;
</script>

<template>
  <el-dialog v-model="graph.graphFullscreenVisible" title="图谱可视化（全屏）" fullscreen append-to-body>
    <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
      <el-button size="small" type="warning" class="back-btn-highlight" @click="graph.closeGraphDialog">返回</el-button>
      <el-segmented
        :model-value="graph.graphView"
        @update:model-value="graph.onGraphViewChange"
        :options="[
          { label: '人物关系网', value: 'people' },
          { label: '剧情事件网', value: 'events' },
          { label: '混合网', value: 'mixed' },
        ]"
      />
      <el-button size="small" :loading="graph.graphLoading" @click="graph.loadGraph">刷新图谱</el-button>
      <el-button size="small" type="success" plain @click="graph.openGraphNodeCreate" :disabled="!novelId">
        新建节点
      </el-button>
      <span class="muted">点击节点可编辑/删除；滚轮缩放，拖拽平移。</span>
    </div>
    <div style="height:10px;"></div>
    <div class="graph-box-fullscreen">
      <div v-if="!novelId" style="color:#909399;">请先选择/创建小说，再查看图谱。</div>
      <div v-else :ref="graph.onGraphRef" class="graph-canvas-fullscreen"></div>
    </div>
  </el-dialog>

  <el-dialog v-model="graph.graphCreateVisible" title="新建图谱节点" width="480px" append-to-body destroy-on-close>
    <el-form label-position="top">
      <el-form-item label="节点类型">
        <el-select v-model="graph.graphCreateType" style="width:100%;">
          <el-option label="人物（character）" value="character" />
          <el-option label="时间线事件（timeline_event）" value="timeline_event" />
          <el-option label="势力（faction）" value="faction" />
        </el-select>
      </el-form-item>
      <template v-if="graph.graphCreateType === 'character'">
        <el-form-item label="角色 ID（唯一）" required>
          <el-input v-model="graph.graphCreateCharId" placeholder="例如：苏瑶 / 虚宇" />
        </el-form-item>
        <el-form-item label="简介（可选）">
          <el-input v-model="graph.graphCreateCharDesc" type="textarea" :rows="3" />
        </el-form-item>
      </template>
      <template v-else-if="graph.graphCreateType === 'timeline_event'">
        <div class="muted" style="margin-bottom:12px; line-height:1.55;">
          事件文案存在 <code>state.json</code> → <code>world.timeline</code>；先后顺序由
          <code>event_relations.json</code> 的 <code>timeline_next</code> 边表示。
          与章节的弱关联靠<strong>相同的 time_slot 文本</strong>（不再写章号）。
          新建后请在图谱中点开该节点，用「上一跳 / 下一跳」连接前后事件。
        </div>
        <el-form-item label="time_slot" required>
          <el-input v-model="graph.graphCreateTlSlot" placeholder="例如：战争后期·反攻前夜" />
        </el-form-item>
        <el-form-item label="summary" required>
          <el-input v-model="graph.graphCreateTlSummary" type="textarea" :rows="3" placeholder="一句话概括该事件" />
        </el-form-item>
      </template>
      <template v-else>
        <el-form-item label="势力名称（唯一）" required>
          <el-input v-model="graph.graphCreateFacName" placeholder="例如：天机阁" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="graph.graphCreateFacDesc" type="textarea" :rows="4" />
        </el-form-item>
      </template>
    </el-form>
    <template #footer>
      <el-button @click="graph.graphCreateVisible = false">取消</el-button>
      <el-button type="primary" :loading="graph.graphCreateSubmitting" @click="graph.submitGraphNodeCreate">创建</el-button>
    </template>
  </el-dialog>

  <el-drawer v-model="graph.graphEditVisible" title="图谱编辑" size="520px" append-to-body>
    <div v-if="!graph.graphEditNode && !graph.graphEditEdge" class="graph-drawer-empty muted">
      <p>请先在图谱中点击一个节点或一条边。</p>
      <el-button type="success" plain size="small" @click="graph.openGraphNodeCreate" :disabled="!novelId">
        新建节点
      </el-button>
    </div>
    <template v-else-if="graph.graphEditEdge">
      <div class="muted">边：<code>{{ graph.graphEditEdge.source }}</code> -> <code>{{ graph.graphEditEdge.target }}</code></div>
      <div class="muted" style="margin-top:4px;">类型：{{ graph.graphEditEdge.type || "relationship" }}</div>
      <div style="height:10px;"></div>
      <template v-if="String(graph.graphEditEdge.type || '').toLowerCase() === 'relationship'">
        <el-form label-position="top">
          <el-form-item label="source">
            <el-select v-model="graph.edgeSourceDraft" filterable placeholder="选择 source">
              <el-option v-for="c in graph.graphCharacterNodeIds" :key="`es-${c}`" :label="c" :value="`char:${c}`" />
            </el-select>
          </el-form-item>
          <el-form-item label="target">
            <el-select v-model="graph.edgeTargetDraft" filterable placeholder="选择 target">
              <el-option v-for="c in graph.graphCharacterNodeIds" :key="`et-${c}`" :label="c" :value="`char:${c}`" />
            </el-select>
          </el-form-item>
          <el-form-item label="怎么关联（label）">
            <el-input v-model="graph.edgeRelLabel" placeholder="例如：师徒 / 敌对 / 欠人情 / 互相利用" />
          </el-form-item>
          <div style="display:flex; gap:8px;">
            <el-button type="primary" @click="graph.saveEdgeRelationship">保存边关系</el-button>
            <el-button type="danger" plain @click="graph.deleteEdgeRelationship">删除这条边</el-button>
          </div>
        </el-form>
      </template>
      <template v-else-if="String(graph.graphEditEdge.type || '').toLowerCase() === 'appear'">
        <el-form label-position="top">
          <el-form-item label="source（角色）">
            <el-select v-model="graph.edgeSourceDraft" filterable placeholder="选择角色">
              <el-option v-for="c in graph.graphCharacterNodeIds" :key="`as-${c}`" :label="c" :value="`char:${c}`" />
            </el-select>
          </el-form-item>
          <el-form-item label="target（章节事件）">
            <el-select v-model="graph.edgeTargetDraft" filterable placeholder="选择章节事件">
              <el-option v-for="c in graph.graphChapterNodeIds" :key="`at-${c}`" :label="c" :value="c" />
            </el-select>
          </el-form-item>
          <el-form-item label="出场/角色定位（label）">
            <el-input v-model="graph.edgeRelLabel" placeholder="例如：出场 / 指挥 / 旁观 / 受伤撤离" />
          </el-form-item>
          <div style="display:flex; gap:8px;">
            <el-button type="primary" @click="graph.saveEdgeRelationship">保存边</el-button>
            <el-button type="danger" plain @click="graph.deleteEdgeRelationship">删除这条边</el-button>
          </div>
        </el-form>
      </template>
      <template v-else-if="String(graph.graphEditEdge.type || '').toLowerCase() === 'timeline_next'">
        <el-form label-position="top">
          <el-form-item label="source（时间线事件）">
            <el-select v-model="graph.edgeSourceDraft" filterable placeholder="选择 source">
              <el-option label="（未安排）当前时间线暂无起始事件" value="" />
              <el-option v-for="t in graph.graphTimelineOptions" :key="`ts-${t.id}`" :label="t.label" :value="t.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="target（下一跳）">
            <el-select v-model="graph.edgeTargetDraft" filterable placeholder="选择 target">
              <el-option label="（未安排）当前时间线暂无下个事件" value="" />
              <el-option v-for="t in graph.graphTimelineOptions" :key="`tt-${t.id}`" :label="t.label" :value="t.id" />
            </el-select>
          </el-form-item>
          <div style="display:flex; gap:8px;">
            <el-button type="primary" @click="graph.saveEdgeRelationship">保存边</el-button>
            <el-button type="danger" plain @click="graph.deleteEdgeRelationship">删除当前边</el-button>
          </div>
          <div class="muted" style="margin-top:8px;">提示：timeline_next 现在直接写入“事件关系表”；手工编辑的连线会保留，未定义下跳才会自动补默认顺序边。</div>
        </el-form>
      </template>
      <template v-else-if="String(graph.graphEditEdge.type || '').toLowerCase() === 'chapter_belongs'">
        <el-form label-position="top">
          <el-form-item label="章节（source）">
            <el-input v-model="graph.edgeSourceDraft" disabled />
          </el-form-item>
          <el-form-item label="归属时间线事件（target）">
            <el-select v-model="graph.edgeTargetDraft" filterable clearable placeholder="选择事件（清空则仅按 time_slot 弱对齐）" style="width:100%;">
              <el-option label="（清空显式归属）" value="" />
              <el-option
                v-for="t in graph.graphTimelineOptions"
                :key="`cb-${t.id}`"
                :label="t.label"
                :value="t.id"
              />
            </el-select>
          </el-form-item>
          <div style="display:flex; gap:8px; flex-wrap:wrap;">
            <el-button type="primary" @click="graph.saveEdgeRelationship" :disabled="!novelId">保存归属</el-button>
            <el-button type="danger" plain @click="graph.deleteEdgeRelationship" :disabled="!novelId">清除显式归属</el-button>
          </div>
          <div class="muted" style="margin-top:8px;">
            多章可指向同一事件；未选事件时，若章节 <code>time_slot</code> 与某时间线事件一致，仍会画出弱对齐边。
          </div>
        </el-form>
      </template>
      <template v-else>
        <div class="muted">该类型边暂不支持修改（可修改 relationship 边）。</div>
      </template>
    </template>
    <template v-else>
      <div class="muted">节点：<code>{{ graph.graphEditNode.id }}</code>（{{ graph.graphEditNode.type }}）</div>
      <div style="height:10px;"></div>

      <template v-if="graph.graphEditNode.type === 'character'">
        <el-form label-position="top">
          <el-form-item label="description">
            <el-input v-model="graph.graphCharDesc" type="textarea" :rows="3" />
          </el-form-item>
          <el-form-item label="goals（每行一条）">
            <el-input v-model="graph.graphCharGoals" type="textarea" :rows="4" />
          </el-form-item>
          <el-form-item label="known_facts（每行一条）">
            <el-input v-model="graph.graphCharFacts" type="textarea" :rows="4" />
          </el-form-item>
          <div style="display:flex; gap:8px; flex-wrap:wrap;">
            <el-button type="primary" @click="graph.saveGraphNodePatch" :disabled="!novelId">保存节点</el-button>
            <el-button type="danger" plain @click="graph.deleteCurrentGraphNode" :disabled="!novelId">删除节点</el-button>
          </div>
        </el-form>

        <el-divider />
        <div style="font-weight:600; margin-bottom:6px;">人物关系（relationship）</div>
        <div class="muted" style="margin-bottom:10px;">修改 source 角色 -> target 角色 的关系描述。</div>
        <el-form label-position="top">
          <el-form-item label="关联到哪个角色（target）">
            <el-select v-model="graph.relTarget" filterable clearable placeholder="选择一个角色">
              <el-option v-for="c in graph.graphCharacterNodeIds" :key="c" :label="c" :value="c" />
            </el-select>
          </el-form-item>
          <el-form-item label="怎么关联（label）">
            <el-input v-model="graph.relLabel" placeholder="例如：师徒 / 敌对 / 欠人情 / 互相利用" />
          </el-form-item>
          <div style="display:flex; gap:8px;">
            <el-button type="primary" @click="graph.setRelationship">新增/更新关系</el-button>
            <el-button type="danger" plain @click="graph.deleteRelationship">删除关系</el-button>
          </div>
        </el-form>
      </template>

      <template v-else-if="graph.graphEditNode.type === 'faction'">
        <el-form label-position="top">
          <el-form-item label="description">
            <el-input v-model="graph.graphFacDesc" type="textarea" :rows="6" />
          </el-form-item>
          <div style="display:flex; gap:8px; flex-wrap:wrap;">
            <el-button type="primary" @click="graph.saveGraphNodePatch" :disabled="!novelId">保存节点</el-button>
            <el-button type="danger" plain @click="graph.deleteCurrentGraphNode" :disabled="!novelId">删除节点</el-button>
          </div>
        </el-form>
      </template>

      <template v-else-if="graph.graphEditNode.type === 'timeline_event'">
        <el-form label-position="top">
          <el-form-item label="time_slot">
            <el-input v-model="graph.graphTlSlot" />
          </el-form-item>
          <el-form-item label="summary">
            <el-input v-model="graph.graphTlSummary" type="textarea" :rows="4" />
          </el-form-item>
          <el-form-item label="上一跳（谁指向当前事件）">
            <el-select v-model="graph.timelinePrevDraft" filterable clearable placeholder="选择上一事件（可空）">
              <el-option label="（未安排）暂无上一事件" value="" />
              <el-option
                v-for="t in graph.graphTimelineOptions"
                :key="`prev-${t.id}`"
                :label="t.label"
                :value="t.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="下一跳（当前事件指向谁）">
            <el-select v-model="graph.timelineNextDraft" filterable clearable placeholder="选择下一事件（可空）">
              <el-option label="（未安排）暂无下一事件" value="" />
              <el-option
                v-for="t in graph.graphTimelineOptions"
                :key="`next-${t.id}`"
                :label="t.label"
                :value="t.id"
              />
            </el-select>
          </el-form-item>
          <div style="display:flex; gap:8px; flex-wrap:wrap; align-items:center;">
            <el-button @click="graph.saveTimelineNeighbors" :disabled="!novelId">保存上下关系</el-button>
            <el-button type="primary" @click="graph.saveGraphNodePatch" :disabled="!novelId">保存节点</el-button>
            <el-button type="danger" plain @click="graph.deleteCurrentGraphNode" :disabled="!novelId">删除节点</el-button>
          </div>
          <div class="muted" style="margin-top:10px;">
            删除时间线事件会移除该事件的稳定 id，并清理所有以该 id 为端点的关系边；其余事件 id 不变。
          </div>
        </el-form>
      </template>

      <template v-else-if="graph.graphEditNode.type === 'chapter_event'">
        <el-form label-position="top">
          <el-form-item label="归属时间线事件（显式）">
            <el-select
              v-model="graph.graphChapterTimelineEventId"
              filterable
              clearable
              placeholder="选择事件；清空则仅按 time_slot 弱对齐"
              style="width:100%;"
            >
              <el-option label="（清空显式归属）" value="" />
              <el-option
                v-for="t in graph.graphTimelineOptions"
                :key="`ch-${t.id}`"
                :label="t.label"
                :value="t.id"
              />
            </el-select>
          </el-form-item>
          <div style="display:flex; gap:8px; flex-wrap:wrap;">
            <el-button type="primary" @click="graph.saveChapterEventTimeline" :disabled="!novelId">保存归属</el-button>
          </div>
          <div class="muted" style="margin-top:10px;">
            同一事件可挂多章；正文文件 <code>ChapterRecord.timeline_event_id</code> 为真源，落盘会同步
            <code>event_relations</code> 中 <code>chapter_belongs</code> 边。
          </div>
        </el-form>
      </template>

      <template v-else>
        <div class="muted">该类型节点暂不支持在图谱内编辑或删除。</div>
      </template>
    </template>
  </el-drawer>
</template>

<style scoped>
.muted {
  color: #909399;
  font-size: 12px;
}
.graph-drawer-empty {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
}
.graph-box-fullscreen {
  height: calc(100vh - 180px);
  border: 1px solid #ebeef5;
  border-radius: 10px;
  background: #fff;
  overflow: hidden;
}
.graph-canvas-fullscreen {
  width: 100%;
  height: 100%;
}
.back-btn-highlight {
  font-weight: 600;
}
</style>
