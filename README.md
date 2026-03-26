## AI Novel Agent — 设定驱动的“长篇写作系统”

这是一个面向长篇网文/系列小说的 **AI 小说代理系统**：以 `settings/*.md` 设定为单一真实来源（SSOT），在“规划 → 写作 → 状态更新 → 落盘归档”的闭环中持续产出章节，并提供 Web 端流式写作体验与知识图谱可视化。

## 亮点（Highlights）
- **设定驱动（Lorebook-first）**：把设定 Markdown 放进 `settings/`，系统自动读取、分标签选择、注入提示词，避免“设定散落在对话里”导致的漂移
- **长篇状态机（Stateful Writing Loop）**：人物 / 世界 / 时间线 / 连续性以 `NovelState` 持久化到 `storage/`，可持续迭代，不依赖一次性上下文
- **流式写作（SSE）**：Web 端通过 `run_stream` 按阶段推送 planning/writing/saving，并实时输出正文增量
- **结构化输出与容错（Pydantic + Repair）**：对 LLM 的 JSON 输出做提取/修复/拆包兼容，并支持 `next_state` 以 **patch** 形式输出后合并，降低“长输出截断 → JSON 解析失败”的崩溃概率
- **知识图谱（Graph API + ECharts）**：后端把人物/事件/势力映射为 nodes/edges，前端力导向图交互查看；支持 people/events/mixed 视图
- **契约可回归（Contract Test）**：针对“区间插入语义（after/before）→ time_slot 推导”提供 pytest 用例，确保前后端契约不漂移

## 功能概览
- **小说管理**：新建小说（弹窗）、选择已有小说（下拉）
- **设定选择**：标签勾选、悬浮 2s 预览、可滚动、支持全文预览弹窗
- **运行模式**
  - `plan_only`：只生成章节要点（beats）并更新状态
  - `write_chapter`：规划 + 生成正文，并落盘章节与状态，同时写入 `outputs/*.txt`
  - `revise_chapter`：修订（MVP：仍按规划+写作流程）
  - `init_state`：保留为高级入口；**正常使用无需手动执行**（后端会自动初始化）
- **插入位置（区间语义）**：用“插入在某事件之后 / 插入在某事件之前”表达区间；也可切换为手动时间段覆盖（二选一）

## 架构一览（Architecture）
```text
Vue3 (Element Plus) ──SSE/REST──> FastAPI
   |                                 |
   | /run_stream (phase + content)   |  NovelAgent (LLM Orchestration)
   | /graph?view=...                  |  Pydantic Models (NovelState/ChapterPlan/Record)
   |                                  |
   └────────────── storage/*.json <───┘
                  outputs/*.txt（正文归档）
```

## 快速开始（Web 推荐）
### 1) 安装依赖
```bash
pip install -r requirements.txt
```

### 2) 配置 API Key
在项目根目录创建 `.env`：
```bash
DEEPSEEK_API_KEY=<your_api_key>
```
充值参考：`https://platform.deepseek.com/top_up`

### 3) 准备设定（lorebook）
在项目根目录创建 `settings/`，放入设定 Markdown（文件名会成为“标签”）：
```text
settings/
  男主及女主.md
  等级设定.md
  怪物大全.md
  辅助体系.md
```

### 4) 启动服务
```bash
python -m uvicorn webapp.server:app --reload --port 8001
```
打开浏览器：`http://127.0.0.1:8001/`

## 旧版脚本（一次性生成）
如需一次性脚本入口：运行 `main.py`（更偏“单次生成”，不含 Web 的交互式能力）。

## 数据与输出（你会在这些目录看到结果）
- **设定输入**：`settings/*.md`
- **状态与章节（JSON）**：`storage/novels/<novel_id>/`
  - `state.json`：NovelState（人物/世界/连续性/时间线等）
  - `chapters/*.json`：每次运行保存的章节记录与 beats
- **正文落盘（txt）**：`outputs/<小说名>_<时间戳>.txt`

## 工程化说明（为什么它更“可维护”）
- **前后端契约**：后端 `RunModeRequest` 以 `insert_after_id/insert_before_id` 为主语义；并提供 pytest 用例回归推导逻辑
- **稳定性策略**：`next_state` 允许输出 patch，落盘前合并为完整状态，避免长 JSON 输出被截断导致失败
- **可观测性**：SSE 输出阶段事件（planning/writing/saving/outputs_written/done/error），前端保留日志且不覆盖正文

## 截图

cli端：

![](./images/Snipaste_2026-03-25_10-48-42.jpg)

网页端：
![](./images/网页端.jpg)
![](./images/图谱.jpg)

## 许可证与版权
- **许可证**：AGPL-3.0-or-later（见 `LICENSE`）
- **作者**：HopoZ（`phmath41@gmail.com`，见 `NOTICE`）