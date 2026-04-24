# TOURMAP（项目进度地图）

模块关系与数据真源见 [`ARCHITECTURE.md`](./ARCHITECTURE.md)；各目录内文件说明见对应 `README.md`。

## DONE（已完成）

- [x] **知识图谱参与 Input 压缩**
  - 将图谱相关信息纳入章节生成前的上下文压缩逻辑，减少无关冗余注入。
  - 手动时间线/事件归属场景下，避免把跨章历史状态整包塞入，降低“状态串章污染”。

- [x] **前后端工作流改造为“先预览、后运行”**
  - 主按钮先生成 Input 预览，再由弹窗“确认并运行”触发流式生成。
  - 运行链路中增加更明确的阶段提示（规划 -> 写作 -> 保存 -> 下章建议）。

- [x] **图谱展示与编辑能力增强（可视化层）**
  - 图谱改为全屏查看入口，提升复杂关系图可读性。
  - 支持节点/边关系编辑、关系删除、时间线前后关系调整等交互能力。
  - 时间线“未安排上/下一跳”支持更直观标识，方便排查断点。

- [x] **存储结构从单状态向表结构演进**
  - 章节、事件、人物相关数据逐步拆分，减少单一叙事快照作为唯一真源的耦合；持久化现为 `storage/novels/<id>/novel.db`（`novel_state`、章节行、四表等）。
  - 运行前预构建章节关联记录，保证“章节属于事件、关联人物”先落地再生成正文。

- [x] **单本小说 SQLite 落地**
  - 图谱与章节编辑仍走 `graph_tables` / `storage` 原 API，底层由 `novel_sqlite` 写入 `novel.db`。

- [x] **Electron Windows 安装包（NSIS + PyInstaller 后端）**
  - 一键脚本 `build-windows-release.bat`；安装版数据在 exe 同级 `data/`；Web 内首次引导、打开输入/输出目录；详见 [electron/ELECTRON_RELEASE.md](../electron/ELECTRON_RELEASE.md)。

- [x] **流式输出与右侧面板体验优化**
  - 右侧状态文案对齐当前真实流程（移除 auto_init 误导信息）。
  - 规划流/正文流/下章建议的空态提示改为运行态动态提示。
  - 右侧输出新增**自动滚动到底**，无需手动拖动滚动条。

- [x] **前端文学暖色主题与续章流程**
  - `theme-literary.css`：纸感背景、Element 变量、顶栏与弹窗样式；`Noto Serif SC`（`index.html`）。
  - 写作/优化等结束后「下章提示」弹窗 → 与「生成正文」相同的 Input 预览链。
  - 表单可选「当前地图」→ `RunModeRequest.current_map` → `build_llm_user_task` 注入约束。

## TODO（待完成）

### 写小说模式现状判断（2026-04）

- 结论：**仍差一点“专业编导感”**。当前已具备“可生成 + 可编辑 + 可观测”，但在“结构约束、自动纠偏、长程回收”上仍偏工具化。
- 主要短板：
  - 写前结构骨架弱（作者仍需手工组织章节目标与伏笔回收）。
  - 写后审计虽已上线（一致性审计 v1），但规则深度不足、未形成强闭环。
  - 图谱虽强可视化，但批量治理/质量审计仍不够“生产级”。

### P0（优先，两周内）

- [x] **一致性审计 v2（从提示走向约束）**
  - [x] `run_stream done` 增加 `block_reasons` 与 `recommended_actions`，高危冲突时阻断“下章续写”自动链。
  - [x] 前端展示审计等级 + 阻断原因 + 修复动作。
  - [x] 增加更多高危规则：时间线反转、角色瞬移、关系突变未给事件依据。

- [x] **章节结构卡（写前强引导）**
  - [x] 预览阶段自动补齐并锁定结构卡：目标 / 冲突 / 转折 / 回收伏笔 / 事件归属（默认无感）。
  - [x] 未满足最小结构项时，提供“继续生成（风险）/返回补齐”二选一，并在后端强校验 `structure_risk_ack`。

- [x] **影子编导 v2（更无感）**
  - [x] 在推荐事件外补充：推荐配角 / 推荐冲突类型 / 推荐回收伏笔（后端 `shadow_director` 策略包）。
  - [x] 默认自动采用细节策略，提供「撤销最近自动导演」一键回滚，作者只需把握总体方向。

### P1（次优，1-2 月）

- [x] **前端布局快改版（中栏与图谱）**
  - [x] 中栏改为四步导演工作台，减少跨栏填写。
  - [x] 图谱采用双形态：中栏切片（默认）+ 全屏工作室（深度编辑）。
  - [x] 运行结果改为抽屉式面板，仅在需要时展开。
  - [x] 保留“少操作，多有意义选择”：冲突类型 / 伏笔策略 / 配角强度三项决策。
  - [x] 后续交互微调：Step 自动流转 + 非当前步骤隐藏 + 顶部当前步骤状态条 + 每步“下一步/上一步”按钮，降低页面过长与误跳转。

- [ ] **图谱治理能力（大图可维护）**
  - 批量编辑：按角色/章节/事件类型批量改边。
  - 质量审计：孤立节点、悬空边、自环、重复关系、断链时间线。
  - 导入导出校验：schema 校验 + dry-run + 错误行定位。

- [ ] **运行可观测性升级**
  - 每次 run 增加 request_id、阶段耗时、错误分类码。
  - 后台记录失败类型分布（网络/模型/解析/持久化）用于持续改进。

- [x] **模型提供商体验对齐 Chatbox**
  - 已完成基础：OpenAI 兼容 provider、模型列表获取、保存前连通性测试。
  - [x] 模型列表缓存：后端 TTL（支持 `force_refresh`）+ 前端会话缓存命中提示。
  - [x] 模型能力标签：`chat / vision / tool / reasoning` 启发式推断并在设置弹窗展示。

### P2（长期，产品化）

- [ ] **连载骨架与回收系统**
  - 主线/支线/伏笔生命周期管理（埋设 -> 推进 -> 回收 -> 验证）。
  - 章节覆盖率与回收率看板，减少后期“坑没填”。

- [ ] **协作与安全**
  - 配置与图谱修改审计日志、快照回滚、多人协作冲突处理。

### 修改名单（按功能分组）

#### 1) 一致性审计 v2
- 后端：
  - `agents/state/consistency_audit.py`
  - `webapp/backend/routes/novels.py`
  - `agents/novel/novel_agent.py`（如需将审计结果参与 prompt）
- 前端：
  - `webapp/frontend/src/App.vue`
  - `webapp/frontend/src/components/RightPanel.vue`
  - `webapp/frontend/src/components/MidFormPanel.vue`

#### 2) 章节结构卡（写前约束）
- 后端：
  - `webapp/backend/schemas.py`
  - `webapp/backend/run_helpers.py`
  - `webapp/backend/routes/novels.py`
- 前端：
  - `webapp/frontend/src/components/MidFormPanel.vue`
  - `webapp/frontend/src/components/dialogs/InputPreviewDialog.vue`
  - `webapp/frontend/src/App.vue`

#### 3) 图谱治理
- 后端：
  - `webapp/backend/routes/graph.py`
  - `agents/persistence/graph_tables.py`
  - `webapp/backend/graph_payload.py`
- 前端：
  - `webapp/frontend/src/composables/useGraph.ts`
  - `webapp/frontend/src/components/graph/GraphDialogs.vue`

#### 4) 观测性与错误分类
- 后端：
  - `webapp/backend/routes/novels.py`
  - `webapp/backend/sse.py`
  - `webapp/backend/app.py`
- 前端：
  - `webapp/frontend/src/App.vue`
  - `webapp/frontend/src/components/RightPanel.vue`

#### 5) Electron 安装包持续维护
- 文档与脚本：
  - `electron/ELECTRON_RELEASE.md`
  - `electron/README.md`
  - `packaging/pyinstaller/README.md`
  - `build-windows-release.bat`