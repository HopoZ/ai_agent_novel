<script setup lang="ts">
import { Search } from "@element-plus/icons-vue";
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
      <el-button size="small" type="primary" plain @click="graph.exportGraphJson" :disabled="!novelId">
        导出 JSON
      </el-button>
      <el-button size="small" type="success" plain @click="graph.openGraphNodeCreate" :disabled="!novelId">
        新建节点
      </el-button>
      <el-input
        v-model="graph.graphSearchQuery"
        class="graph-search-input"
        :class="{ 'graph-search-input--active': !!(graph.graphSearchQuery || '').trim() }"
        clearable
        placeholder="搜索节点（id、名称、类型、简介等）"
        @clear="graph.clearGraphSearch"
        @keyup.enter="graph.focusNextGraphSearchMatch"
        @keyup.shift.enter="graph.focusPrevGraphSearchMatch"
      >
        <template #prefix>
          <el-icon class="graph-search-prefix" aria-hidden="true"><Search /></el-icon>
        </template>
      </el-input>
      <el-button size="small" @click="graph.focusNextGraphSearchMatch" :disabled="!novelId">
        下一匹配
      </el-button>
      <el-button size="small" @click="graph.focusPrevGraphSearchMatch" :disabled="!novelId">
        上一匹配
      </el-button>
      <el-tag v-if="(graph.graphSearchQuery || '').trim()" size="small" type="warning" effect="light">
        命中 {{ graph.graphSearchMatchCount }} 个节点
      </el-tag>
      <el-button size="small" text type="primary" @click="graph.clearGraphSearch">清空搜索</el-button>
      <span class="muted">点击节点可编辑/删除；滚轮缩放，拖拽平移。有搜索词时未命中节点变淡，边随之减弱。</span>
    </div>
    <div style="height:10px;"></div>
    <div class="graph-admin-panel">
      <div class="graph-filter-grid">
        <div class="graph-filter-col">
          <el-text size="small" class="muted graph-filter-title">节点筛选</el-text>
          <el-checkbox-group v-model="graph.graphNodeTypeFilters" class="graph-filter-checks">
            <el-checkbox label="character">人物</el-checkbox>
            <el-checkbox label="timeline_event">时间线事件</el-checkbox>
            <el-checkbox label="chapter_event">章节事件</el-checkbox>
            <el-checkbox label="faction">势力</el-checkbox>
          </el-checkbox-group>
        </div>
        <div class="graph-filter-col">
          <el-text size="small" class="muted graph-filter-title">边筛选</el-text>
          <el-checkbox-group v-model="graph.graphEdgeTypeFilters" class="graph-filter-checks">
            <el-checkbox label="relationship">relationship</el-checkbox>
            <el-checkbox label="appear">appear</el-checkbox>
            <el-checkbox label="timeline_next">timeline_next</el-checkbox>
            <el-checkbox label="chapter_belongs">chapter_belongs</el-checkbox>
          </el-checkbox-group>
        </div>
      </div>
      <el-space wrap style="margin-top:8px;">
        <el-checkbox v-model="graph.graphOnlyIsolatedNodes">只看孤立节点</el-checkbox>
        <el-button size="small" text type="primary" @click="graph.resetGraphFilters">重置筛选</el-button>
        <el-tag size="small">节点 {{ graph.graphStats.nodeTotal }}</el-tag>
        <el-tag size="small" type="success">边 {{ graph.graphStats.edgeTotal }}</el-tag>
        <el-tag size="small">人物 {{ graph.graphStats.nodeByType.character }}</el-tag>
        <el-tag size="small">时间线 {{ graph.graphStats.nodeByType.timeline_event }}</el-tag>
        <el-tag size="small">章节 {{ graph.graphStats.nodeByType.chapter_event }}</el-tag>
        <el-tag size="small">势力 {{ graph.graphStats.nodeByType.faction }}</el-tag>
      </el-space>
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
              <el-option v-for="c in graph.relationTargetOptions" :key="c" :label="c" :value="c" />
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
.graph-admin-panel {
  border: 1px solid #ebeef5;
  border-radius: 10px;
  padding: 10px 12px;
  background: #fcfcfd;
}
.graph-filter-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(260px, 1fr));
  gap: 10px 16px;
}
.graph-filter-col {
  border: 1px solid #eef1f6;
  border-radius: 8px;
  background: #fff;
  padding: 8px 10px;
}
.graph-filter-title {
  display: inline-block;
  margin-bottom: 6px;
  font-weight: 600;
}
.graph-filter-checks {
  display: grid;
  grid-template-columns: repeat(2, minmax(120px, 1fr));
  gap: 6px 8px;
}
@media (max-width: 980px) {
  .graph-filter-grid {
    grid-template-columns: 1fr;
  }
}
.graph-canvas-fullscreen {
  width: 100%;
  height: 100%;
}
.back-btn-highlight {
  font-weight: 600;
}
.graph-search-input {
  width: min(280px, 100%);
  max-width: 320px;
  flex-shrink: 0;
}
.graph-search-prefix {
  color: #a67c2a;
  font-size: 16px;
  margin-right: 2px;
}
.graph-search-input :deep(.el-input__wrapper) {
  background: linear-gradient(180deg, #fffef9 0%, #faf4e8 100%);
  border-radius: 10px;
  box-shadow:
    0 0 0 1px rgba(196, 165, 116, 0.65) inset,
    0 2px 10px rgba(74, 102, 118, 0.08);
  transition:
    box-shadow 0.2s ease,
    background 0.2s ease;
}
.graph-search-input :deep(.el-input__wrapper:hover) {
  box-shadow:
    0 0 0 1px #c4a574 inset,
    0 4px 14px rgba(184, 134, 11, 0.12);
}
.graph-search-input :deep(.el-input__wrapper.is-focus) {
  background: #fffdf8;
  box-shadow:
    0 0 0 2px #b8860b inset,
    0 0 0 4px rgba(184, 134, 11, 0.18),
    0 6px 20px rgba(184, 134, 11, 0.15);
}
.graph-search-input--active :deep(.el-input__wrapper:not(.is-focus)) {
  box-shadow:
    0 0 0 2px rgba(184, 134, 11, 0.45) inset,
    0 2px 12px rgba(184, 134, 11, 0.14);
}
.graph-search-input :deep(.el-input__inner::placeholder) {
  color: #a8987a;
}
</style>
