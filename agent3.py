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
        super().__init__(instructions=(
            "You're an AI call assistant for NBS UPO office. "
            "You take calls, extract messages, and match appropriate mailboxes."
        ))

async def extract_caller_info(llm, text: str) -> dict:
    # 系统角色与任务流程
    system_msg = {
        "role": "system",
        "content": (
            "You are an AI telephone assistant for NBS UPO office.\n"
            "When a call starts, you first say:\n"
            "  \"this is nbs upo office, how may i help you\"\n"
            "Then guide the caller through the following steps (in any natural order but covering all):\n"
            "  1. Ask for and record caller’s name (name).\n"
            "  2. Ask for and record caller’s identity (identity): student or external_company.\n"
            "     - If student, also record student_id.\n"
            "     - If external_company, also record company_name and company_phone.\n"
            "  3. Ask for and record caller’s email (email).\n"
            "  4. Ask for and record call purpose (purpose_text), and classify it as one of:\n"
            f"     {list(MAPPING.keys())}\n"
            "  5. Give the caller appropriate email address and tell the caller: “Your information will be forwarded to the relevant department.”\n"
            "  6. If you lack permission to help directly, say: "
            "“I’m sorry, I don’t have permission to help directly; I will record and forward this to the relevant department.”\n"
            "  7. If any required field cannot be determined, ask up to 2 more times (3 total), e.g.:\n"
            "     “Sorry, I didn’t catch that. Can you spell your name?”\n"
            "  8. If after 3 attempts any field is still missing, stop and return action: transfer_to_human.\n\n"
            "Finally, only return a single JSON object with exactly these keys:\n"
            "  name, identity, student_id, company_name, company_phone, email,\n"
            "  purpose_type, purpose_text, action\n"
            "Set any non‑applicable field to \"unknown\"."
        )
    }

    # Few‑Shot 示例
    examples = [
        {
            "role": "user",
            "content": (
                "Transcript:\n"
                "\"Hello, I’m Zhang Wei, a student. My student ID is 20230001, "
                "and I need help resetting my password. My email is zhangwei@example.com.\""
            )
        },
        {
            "role": "assistant",
            "content": json.dumps({
                "name": "Zhang Wei",
                "identity": "student",
                "student_id": "20230001",
                "company_name": "unknown",
                "company_phone": "unknown",
                "email": "zhangwei@example.com",
                "purpose_type": "technical_support",
                "purpose_text": "reset password",
                "action": "complete"
            })
        },
        {
            "role": "user",
            "content": (
                "Transcript:\n"
                "\"Hi, I’m from Acme Corp. My email is help@acme.com. "
                "I want to inquire about your pricing.\""
            )
        },
        {
            "role": "assistant",
            "content": json.dumps({
                "name": "unknown",
                "identity": "external_company",
                "student_id": "unknown",
                "company_name": "Acme Corp",
                "company_phone": "unknown",
                "email": "help@acme.com",
                "purpose_type": "pricing_inquiry",
                "purpose_text": "inquire about pricing",
                "action": "complete"
            })
        },
        {
            "role": "user",
            "content": (
                "Transcript:\n"
                "\"I need assistance, but I’ll only say my name when you ask me to spell it.\""
            )
        },
        {
            "role": "assistant",
            "content": "Can you please spell your name for me?"
        }
    ]

    # 构造实际用户消息
    user_msg = {
        "role": "user",
        "content": (
            "Transcript:\n"
            f"\"{text}\"\n\n"
            "Please follow the system instructions and output the required JSON based on the conversation transcript."
        )
    }

    # 调用模型并解析
    resp = llm.chat.completions.create(
        model="gpt-4o-mini",
        messages=[system_msg] + examples + [user_msg],
        temperature=0.1,
    )
    return json.loads(resp.choices[0].message.content)

async def entrypoint(ctx: JobContext):
    # 连接到 LiveKit 房间
    await ctx.connect()

    # 创建 RealtimeModel
    llm = RealtimeModel(
        model="gpt-4o-realtime-preview",
        voice="coral",
        temperature=0.6,
    )

    client = OpenAI()
    text_llm = client

    # 启动 Agent 会话
    session = AgentSession(llm=llm)
    await session.start(room=ctx.room, agent=Assistant())

    # 初始打招呼
    await session.generate_reply(instructions="Greet and assist users.")

    # 监听用户语音转文本后的回调
    async def handle_transcribed(event):
        text = event.transcript

        # 抽取、播报、挂断等原有逻辑……
        caller_info = await extract_caller_info(text_llm, text)
        await session.generate_reply(
            instructions=f"Hi, this is NBS UPO office. "
        )
        if caller_info.get("action") == "transfer_to_human":
            await session.generate_reply(instructions="Transferring to human agent now.")
        else:
            await session.generate_reply(instructions="Thank you. Goodbye.")
        await hangup_call()

    # 2. 用同步函数注册到 .on()，在里面 create_task
    def on_user_input_transcribed(event):
        # 这里 session、llm、extract_caller_info 都需要在外层作用域可见
        asyncio.create_task(handle_transcribed(event))

    # 3. 注册时用同步函数
    session.on("user_input_transcribed", on_user_input_transcribed)

async def hangup_call():
    ctx = get_job_context()
    if ctx is None:
        return
    await ctx.api.room.delete_room(
        api.DeleteRoomRequest(room=ctx.room.name)
    )

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
