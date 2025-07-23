from dotenv import load_dotenv
import os
import json
import asyncio

from openai import OpenAI
from livekit import agents
from livekit.agents import AgentSession, Agent, JobContext
from livekit.plugins.openai.realtime import RealtimeModel
from livekit import api
from livekit.agents import get_job_context

# 加载环境变量
load_dotenv()

# 读取 mapping.json
mapping_path = os.path.join(os.path.dirname(__file__), "mapping.json")
with open(mapping_path, "r", encoding="utf-8") as f:
    MAPPING = json.load(f)

class Assistant(Agent):
    def __init__(self) -> None:
        # 将长提示词作为系统级指令注入给实时语音模型
        long_prompt = (
            "You are an AI telephone assistant for NBS UPO office.\n"
            "When a call starts, you first say:\n"
            "  \"this is nbs upo office, how may i help you\"\n"
            "Then guide the caller through the following steps (in any natural order but covering all):\n"
            "  1. Ask for and record caller’s name (name).\n"
            "  2. Ask for and record caller’s identity (identity): student or external_company.\n"
            "     - If student, also record student_id.\n"
            "     - If external_company, also record company_name and company_phone.\n"
            "  3. Ask for and record caller’s email (email).\n"
            "  4. Ask for and record call purpose (purpose_text), and classify it as one of: \n"
            f"     {list(MAPPING.keys())}\n"
            "  5. Tell the caller: “Your information will be forwarded to the relevant department.”\n"
            "  6. If you lack permission to help directly, say: \"I’m sorry, I don’t have permission to help directly; I will record and forward this to the relevant department.\"\n"
            "  7. If any required field cannot be determined, ask up to 2 more times (3 total), e.g.:\n"
            "     \"Sorry, I didn’t catch that. Can you spell your name?\"\n"
            "  8. If after 3 attempts any field is still missing, stop and return action: transfer_to_human.\n\n"
            "Finally, only return a single JSON object with exactly these keys:\n"
            "  name, identity, student_id, company_name, company_phone, email, purpose_type, purpose_text, action\n"
            "Set any non‑applicable field to \"unknown\"."
        )
        super().__init__(instructions=long_prompt)

async def extract_caller_info(llm, text: str) -> dict:
    # 系统角色与任务流程
    system_msg = {
        "role": "system",
        "content": (
            # 保留用于文本模型的长提示词和 few-shot 示例
            "..."
        )
    }
    examples = [ ... ]  # few-shot 示例省略
    user_msg = { ... }  # 构造实际用户消息

    # 调用文本模型生成 JSON
    resp = llm.chat.completions.create(
        model="gpt-4o-mini",
        messages=[system_msg] + examples + [user_msg],
        temperature=0.1,
    )
    return json.loads(resp.choices[0].message.content)

async def entrypoint(ctx: JobContext):
    # 连接到 LiveKit 房间
    await ctx.connect()

    # 实时语音模型
    llm = RealtimeModel(
        model="gpt-4o-realtime-preview",
        voice="coral",
        temperature=0.6,
    )

    # 纯文本 OpenAI 客户端
    client = OpenAI()
    text_llm = client

    # 启动 Agent 会话并注入系统提示
    session = AgentSession(llm=llm)
    await session.start(room=ctx.room, agent=Assistant())

    # 先播打招呼，确保 complete 后再注册回调
    await session.generate_reply(instructions="Greet and assist users.")

    # 只有在打招呼完成后才注册回调，避免冲突
    def on_user_input_transcribed(event):
        asyncio.create_task(handle_transcribed(event))
    session.on("user_input_transcribed", on_user_input_transcribed)

    async def handle_transcribed(event):
        text = event.transcript

        # 调用文本模型解析
        caller_info = await extract_caller_info(text_llm, text)
        # 合并内部确认和结束（或转接）为一次回复，避免竞态
        instruction = "Got it, I've recorded your information. "
        if caller_info.get("action") == "transfer_to_human":
            instruction += "Transferring to human agent now."
        else:
            instruction += "Thank you. Goodbye."
        await session.generate_reply(instructions=instruction)
        await hangup_call()

async def hangup_call():
    ctx = get_job_context()
    if ctx is None:
        return
    await ctx.api.room.delete_room(
        api.DeleteRoomRequest(room=ctx.room.name)
    )

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
