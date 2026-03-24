import os
from datetime import datetime
from dotenv import load_dotenv

# 推荐使用 init_chat_model 保持跨供应商一致性
from langchain.chat_models import init_chat_model
from langchain.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage

# =========================
# 1️⃣ 配置环境
# =========================
load_dotenv()
if not os.getenv("DEEPSEEK_API_KEY"):
    raise ValueError("请在 .env 文件中添加 DEEPSEEK_API_KEY")

output_dir = "outputs"
os.makedirs(output_dir, exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_file = os.path.join(output_dir, f"deepseek_v1_output_{timestamp}.txt")

# =========================
# 2️⃣ 初始化 Model (LangChain v1 推荐方式)
# =========================
# 指定 output_version="v1" 以使用标准的 content_blocks
model = init_chat_model(
    "deepseek-chat",
    model_provider="openai", # DeepSeek 兼容 OpenAI 格式
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com/v1",
    temperature=0,
    output_version="v1"
)

# =========================
# 3️⃣ 定义工具 (使用标准装饰器)
# =========================
def get_current_time(location: str) -> str:
    """获取指定位置的当前时间。"""
    # 这是一个示例工具，你可以根据需求替换
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# 将工具绑定到模型
model_with_tools = model.bind_tools([get_current_time])

# =========================
# 4️⃣ 构建消息序列并执行
# =========================
if __name__ == "__main__":
    user_prompt = "你是一个小说创作助手。请帮我写一段关于AI小说创作的创意四千字文本，包含玄幻元素，直接开始创作，不要进行开场白或反问。"

    # 按照文档推荐，使用 Message 对象列表
    messages = [
        SystemMessage("你是一个精通科幻创作的资深作家，语气要优雅且富有想象力。"),
        HumanMessage(user_prompt)
    ]

    # 调用模型
    response = model_with_tools.invoke(messages)

    # 检查是否有工具调用 (Tool Calls)
    # 如果模型决定调用工具，处理逻辑如下：
    if response.tool_calls:
        for tool_call in response.tool_calls:
            # 模拟执行工具
            result = get_current_time(tool_call["args"].get("location", "Unknown"))
            # 将工具结果反馈给模型
            messages.append(response) # 先存入 AI 的工具调用请求
            messages.append(ToolMessage(content=result, tool_call_id=tool_call["id"]))
            # 再次调用模型获取最终文案
            response = model_with_tools.invoke(messages)

    # =========================
    # 5️⃣ 结果持久化与元数据提取
    # =========================
    with open(output_file, "a", encoding="utf-8") as f:
        f.write(f"=== [Timestamp: {timestamp}] ===\n")
        f.write(f"User Prompt: {user_prompt}\n\n")
        f.write(f"AI Content:\n{response.content}\n\n")

        # 利用 v1 提供的 usage_metadata
        if hasattr(response, 'usage_metadata'):
            usage = response.usage_metadata
            f.write(f"--- Token Usage ---\n")
            f.write(f"Total Tokens: {usage.get('total_tokens')}\n")
            f.write(f"Input Tokens: {usage.get('input_tokens')}\n")
            f.write(f"Output Tokens: {usage.get('output_tokens')}\n")

    print(f"✨ 创作完成！结果已存至: {output_file}")
    print(f"📊 消耗总 Token: {response.usage_metadata.get('total_tokens')}")