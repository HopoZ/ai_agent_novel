一个AI agent工作流，用于创建小说章节。

也可以改造设定用于各种需要整体架构的地方。

# 特点

- 无需网页端次次输入，只需在settings目录放入设定文档，AI agent就会根据设定文档进行工作。
- 自动生成prompt，自动调用API，自动总结经验，自动调整策略。


# 准备

安装依赖：
```
pip install -r requirements.txt
```
# 根目录创建.env文件

填入`DEEPSEEK_API_KEY=<your_api_key>`

# DEEPSEEK_API_KEY购买网址

[https://platform.deepseek.com/top_up](https://platform.deepseek.com/top_up)

# 根目录创建settings目录放入各种设定的markdown文档

比如
```
人物设定.md
等级设定.md
...
```

接着你可以二选一：

1. 旧版脚本（一次性生成）
   - 运行[main.py](./main.py)

2. Web 版（成熟 agent，带世界状态持久化 + 用户可选模式）
   - 启动：
     - `uvicorn webapp.server:app --reload --port 8000`
   - 打开浏览器：
     - `http://127.0.0.1:8000/`

Web 支持的模式：
- `init_state`：初始化完整人物/世界状态（首次必须做）
- `plan_only`：只规划 beats + 更新 next_state（不生成正文）
- `write_chapter`：规划 beats + 生成正文，并落盘章节与 next_state
- `revise_chapter`：对指定章节进行修订（MVP 版本仍按“规划+写作”流程）

# 结果如图所示

![](./images/Snipaste_2026-03-25_10-48-42.jpg)

# TODO

- 长期复杂文章（数万字）记忆（会在 `recent_summaries` 与 state 压缩策略上继续增强）

# 许可证与版权

- 许可证：AGPL-3.0-or-later（见 `LICENSE`）
- 作者：HopoZ（`phmath41@gmail.com`，见 `NOTICE`）