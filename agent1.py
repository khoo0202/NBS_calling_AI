from dotenv import load_dotenv
import os, json
import asyncio

from livekit import agents
from livekit.agents import AgentSession, Agent, JobContext
from livekit.plugins.openai.realtime import RealtimeModel

# 加载 .env 中的环境变量
load_dotenv()

mapping_path = os.path.join(os.path.dirname(__file__), "mapping.json")
with open(mapping_path, "r", encoding="utf-8") as f:
    MAPPING = json.load(f)

class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions="You're an AI call assistant who takes calls, extracts messages, and matches appropriate mailboxes.")

async def entrypoint(ctx:JobContext):
    # 连接到 LiveKit 房间
    await ctx.connect()

    # 创建一个 RealtimeModel 实例
    llm = RealtimeModel(
        model="gpt-4o-realtime-preview",
        voice="coral",
        temperature=0.2,
    )

    # 创建并启动会话
    session = AgentSession(llm=llm)
    await session.start(
        room=ctx.room,
        agent=Assistant()
    )

    # 生成一条初始欢迎语
    await session.generate_reply(
        instructions="向用户打招呼并提供帮助。"
    )

'''async def extract_caller_info(llm, text: str) -> dict:
    prompt = f"""
    请从下面这段话中提取：
    1. 来电者姓名 (name)
    2. 来电者身份 (identity)
    3. 通话目的 (purpose_text)，并将其归类到以下类型之一(purpose_type)：{list(MAPPING.keys())}
    
    输入：“{text}”
    输出 JSON，例如：
    {{
      "name": "张三",
      "identity": "采购部经理",
      "purpose_type": "technical_support",
      "purpose_text": "我的系统无法登录"
    }}
    """
    resp = await llm.chat_completion(messages=[{"role":"user","content":prompt}])
    return json.loads(resp.choices[0].message.content)
'''

if __name__ == "__main__":
    # 启动 Worker
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))

