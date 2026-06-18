import asyncio
from agent_framework import Agent, Message, Content
from azure_clients.azure_client import get_client


async def _generate_title_async(question: str) -> str:
    client = get_client()
    try:
        prompt = f"""
Generate a very short title (3-5 words max) for a chat session that starts with this question:

"{question}"

Rules:
- 3 to 5 words only
- No punctuation
- No quotes
- Descriptive and specific
- Return ONLY the title, nothing else

Examples:
Question: "How many franchises are in Japan?"
Title: Japan Franchise Count

Question: "What are total sales this quarter?"
Title: Quarterly Sales Total

Question: "How are you?"
Title: General Greeting
"""
        message = Message(role="user", contents=[Content.from_text(prompt)])
        agent   = Agent(
            client=client,
            instructions="Generate a short 3-5 word chat title. Return only the title."
        )
        response = ""
        async for event in agent.run(message, stream=True):
            if hasattr(event, "text") and event.text:
                response += event.text
        return response.strip().strip('"').strip("'")
    finally:
        if hasattr(client, "close"):
            await client.close()


def generate_chat_title(question: str) -> str:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    title = loop.run_until_complete(_generate_title_async(question))
    loop.close()
    return title or question[:30]