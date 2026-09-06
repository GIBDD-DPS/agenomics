"""
Шаблон под AgentScope (Alibaba), проверено по актуальной документации
(AgentScope 2.0, релиз май 2026).
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    import asyncio
    import os
    from agentscope.agent import ReActAgent
    from agentscope.formatter import OpenAIChatFormatter
    from agentscope.memory import InMemoryMemory
    from agentscope.message import Msg
    from agentscope.model import OpenAIChatModel

    async def _run():
        agent = ReActAgent(
            name="Assistant",
            sys_prompt="You are a helpful assistant.",
            model=OpenAIChatModel(
                model_name="gpt-4o-mini",  # замените на вашу модель
                api_key=os.environ.get("OPENAI_API_KEY"),
            ),
            formatter=OpenAIChatFormatter(),
            memory=InMemoryMemory(),
        )
        msg = Msg(name="User", content="Что такое AgentScope?", role="user")  # замените на вашу задачу
        response = await agent(msg)
        return response

    result = asyncio.run(_run())
    print(result.content)
    return result
