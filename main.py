# cli版逻辑

import os
from datetime import datetime
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain.messages import HumanMessage, SystemMessage, AIMessage
from agents.loader import LoreLoader
import winsound


class WritingAgent:
    def __init__(self):
        load_dotenv()

        # 初始化模型
        self.model = init_chat_model(
            "deepseek-chat",
            model_provider="openai",
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com/v1",
            temperature=0.8,
            output_version="v1",
            max_tokens=10000
        )

    def parse_content(self, response: AIMessage) -> str:
        """自动解读 v1 格式块，只提取纯文本正文"""
        if isinstance(response.content, str):
            return response.content
        return "".join(
            block.get("text", "")
            for block in response.content
            if isinstance(block, dict) and block.get("type") == "text"
        )

    def write(self, user_task: str):
        # 使用模块的功能：获取百科全书
        lore_loader = LoreLoader()
        lore_context = lore_loader.get_all_lore()

        system_instruction = f"""你是一个顶尖的网文创作Agent。
你的创作必须【严丝合缝】地符合以下百科设定的框架。

{lore_context}

【创作指令】：
- 直接开始正文叙述，不要任何废话。
- 逻辑严密，必须符合百科中的等级、人物、怪物设定背景。
"""

        messages = [
            SystemMessage(content=system_instruction),
            HumanMessage(content=user_task)
        ]

        print("Agent 正在加载百科设定...")
        response = self.model.invoke(messages)
        print(f"消耗总 Token: {response.usage_metadata.get('total_tokens')}")

        return self.parse_content(response), response.usage_metadata


# 执行主程序

if __name__ == "__main__":
    # 初始化 Agent
    agent = WritingAgent()

    # 设定具体创作任务
    task = "描述依据百科全书丰富为某一多于四千字的章节。最后总结一下你在章节中对设定(人物，怪物，体系等)的拓展或补充。"

    # 执行并获取解析后的文本
    content, usage = agent.write(task)

    # 保存
    output_file = f"outputs/novel_{datetime.now().strftime('%m%d_%H%M%S')}.txt"
    os.makedirs("outputs", exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(content)

    winsound.Beep(1000, 500)  # windows的语音库，提示任务完成
    print(f"任务完成！设定已自动从 settings 目录同步。")
    print(f"创作完成！结果已存至: {output_file}")