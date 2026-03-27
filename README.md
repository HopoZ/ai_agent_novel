## AI Novel Agent（README1）

一个面向长篇网文/系列叙事的工程化写作系统。  
系统以 `settings/*.md` 作为设定单一真实来源（SSOT），围绕 `plan -> write -> state update -> persist` 建立可持续迭代的创作闭环，并提供可观测、可回放、可维护的 Web 写作工作流。

项目预览:
![](./images/网页端.jpg)
![](./images/图谱.jpg)

## 1. 设计目标

- **连续性优先**：写作不是“一次性生成”，而是状态机驱动的长期演进
- **设定优先**：设定文件化、标签化、可控注入，避免设定漂移
- **可观测优先**：输入预览、阶段事件、token 消耗全链路可见
- **失败可恢复**：结构化输出 + patch 合并，减少长输出导致的崩溃

## 2. 系统能力矩阵

### 2.1 叙事状态管理（Stateful Narrative Engine）
- 通过 `NovelState` 维持运行态连续性摘要：
  - 人物状态（关系、目标、已知事实、位置）
  - 世界规则（规则、阵营、开放问题）
  - 时间线（timeline）
  - 连续性约束（time_slot / POV / 出场角色）
- 存储路径：`storage/novels/<novel_id>/state.json`
- 重要：`state.json` 是**运行态摘要/快照**，人物/事件关系的**真源**来自图谱表（见「关键数据资产」）

### 2.2 写作链路（Plan + Draft）
- `plan_chapter` 生成结构化 `ChapterPlan`
- `write_chapter_text(_stream)` 生成正文（支持流式输出）
- 写作结果结构化落盘：`storage/novels/<id>/chapters/*.json`
- 同步输出纯文本归档：`outputs/*.txt`

### 2.3 Lore 摘要与注入策略
- 摘要由 LLM 生成（非规则抽取）
- 摘要缓存按 **单 tag 粒度**：`llm_tag_v1`
- 运行链路使用 `lore_tags`，不依赖 `lore_summary_id`
- 注入策略：
  1. 优先命中每个 tag 的摘要缓存
  2. 未命中则回退该 tag 原文（信息不丢）
- 摘要接口返回结构化结果：`tag_summaries: [{ tag, summary }]`

### 2.4 上下文压缩策略
- 默认仅注入相邻相关两章
- 手动设置 `time_slot_override` 时，不注入章节 JSON 上下文
- 章节 JSON `content` 不作为核心上下文输入，避免 token 爆炸

### 2.5 可观测性与交互
- SSE 阶段事件：`planning -> writing -> saving -> done`
- 前端单按钮流程：先生成 Input 预览，再确认运行（避免“填完直接烧 token”）
- `/preview_input` 可查看本次真实拼装输入
- 悬浮预览 `compact=1` 显示 tag 摘要（无缓存提示先生成）
- 图谱视图：`people / events / mixed`
- 右侧输出：正文/规划流/下章建议均为流式增量，并支持**自动滚动到底**
- 支持前端中止生成（中止后端尽快停止，以节省 token）

## 3. 运行模式

| Mode | 语义 |
|---|---|
| `init_state` | 初始化世界状态（显式执行；写作链路不会自动初始化） |
| `plan_only` | 仅生成章节规划并推进状态 |
| `write_chapter` | 规划 + 正文生成 + 落盘 |
| `revise_chapter` | 修订（当前沿用规划+写作链路） |

注意：若 `state.meta.initialized=false`，写作链路会直接报错提示先初始化（避免“隐式初始化造成规划/写作上下文冲突”）。

## 4. 架构分层

```text
[Presentation]
Vue3 + Element Plus + ECharts
  - 标签树/角色选择/输入预览
  - SSE 流式正文
  - 图谱可视化（全屏查看 + 节点/边编辑）
        |
        v
[API]
FastAPI (webapp/server.py)
  - /api/novels/*
  - /api/lore/*
  - /api/novels/*/graph
  - /api/novels/*/run_stream
        |
        v
[Domain]
NovelAgent (agents/novel_agent.py)
  - build_lore_summary_llm
  - plan_chapter / write_chapter_text
  - merge_state
  - preview_input
        |
        v
[Data]
settings/*.md
storage/lore_summaries/*.json
storage/novels/<id>/{state.json, chapters/*.json, character_entities.json, character_relations.json, event_entities.json, event_relations.json}
outputs/*.txt
```

## 5. 关键数据资产

- `settings/**/*.md`：静态设定源
- `storage/lore_summaries/*.json`：tag 摘要缓存
- `storage/novels/<id>/state.json`：运行态摘要（供模型连续性使用，**非关系真源**）
- `storage/novels/<id>/chapters/*.json`：章节结构化记录（每章一表，source-of-truth 用于刷新运行态摘要字段）
- `storage/novels/<id>/character_entities.json`：人物实体表
- `storage/novels/<id>/character_relations.json`：人物关系表
- `storage/novels/<id>/event_entities.json`：事件实体表
- `storage/novels/<id>/event_relations.json`：事件关系表
- `outputs/*.txt`：正文归档

## 6. 接口总览（高频）

- `POST /api/lore/summary/build`
  - 入参：`{ tags: string[], force?: boolean }`
  - 返回：`tag_summaries`
- `GET /api/lore/preview?tag=...&compact=1`
  - 返回指定 tag 摘要预览
- `POST /api/novels/{novel_id}/run_stream`
  - SSE 流式执行
- `POST /api/novels/{novel_id}/preview_input`
  - 返回本次组装输入（不调用模型）

## 7. 快速开始

### 7.1 安装依赖
```bash
pip install -r requirements.txt
```

### 7.2 配置密钥
在项目根目录创建 `.env`：
```bash
DEEPSEEK_API_KEY=<your_api_key>
```

### 7.3 准备设定
把 Markdown 设定放入 `settings/`（目录路径即标签空间）。

### 7.4 启动服务
```bash
python -m uvicorn webapp.server:app --reload --port 8000
```
访问：`http://127.0.0.1:8000/`

## 8. 常见问题

### 8.1 为什么 token 依然偏高
- lore 体积仍可能较大（尤其未命中摘要缓存时）
- 任务描述过长会放大 state/lore 注入体积
- 建议先生成 tag 摘要，再执行章节生成

## 9. 工程实践建议

- **先摘要后写作**：先执行“生成当前Tag摘要”，再运行章节生成
- **按章控范围**：每章任务仅描述本章目标，避免跨多章超大任务
- **以四表为关系事实源**：人物/事件实体与关系使用四表，`state.json` 用作运行态摘要
- **图谱先落表再生成**：章节“归属事件 + 关联人物”的选择应先写入图谱表，再进入 plan/write（减少 LLM 自行绑定造成的不一致）

## 10. 许可证

- AGPL-3.0-or-later 见[./LICENSE](./LICENSE)
- 作者信息见 [./NOTICE](./NOTICE)

