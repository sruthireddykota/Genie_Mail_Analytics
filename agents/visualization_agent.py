import asyncio
import json

from agent_framework import Agent, Message, Content
from azure_clients.azure_client import get_client
from utils.logger import get_logger

logger=get_logger()

class VisualizationAgent:

    def __init__(self):
        self.client = get_client()

    async def analyze(self, question, sql, dataframe_columns, row_count):
        try:
            prompt = f"""
You are an AI visualization reasoning assistant.

Your tasks:
1. Analyze the user question
2. Analyze the SQL query
3. Analyze dataframe columns and row count
4. Decide the BEST chart type, or "none" if no chart fits
5. Decide x-axis and y-axis
6. Return ONLY valid JSON

Question:
{question}

SQL:
{sql}

Available DataFrame Columns:
{dataframe_columns}

Row Count: {row_count}

Visualization Rules:
- Category comparison (e.g. sales by product, franchises by country) -> bar
- Time/date trend (e.g. sales by month, growth over quarters) -> line
- Distribution/percentage breakdown across few categories (under 8 categories) -> pie
- If data doesn't clearly fit bar, line, or pie -> visualization = "none"

IMPORTANT:
- Use ONLY columns from dataframe_columns
- x_axis and y_axis MUST match dataframe column names exactly
- Never return "table" or "metric" as visualization type
- Return ONLY JSON
- No markdown
- No explanation

JSON Format:
{{
    "visualization": "",
    "title": "",
    "x_axis": "",
    "y_axis": "",
    "summary": ""
}}
"""

            message = Message(
                role="user",
                contents=[Content.from_text(prompt)]
            )

            agent = Agent(
                client=self.client,
                instructions="""
You are a visualization reasoning agent.
Return ONLY valid JSON. No markdown. No explanation.
Only choose bar, line, pie, or none.
"""
            )

            final_response = ""
            async for event in agent.run(message, stream=True):
                if hasattr(event, "text") and event.text:
                    final_response += event.text

            return final_response

        finally:
            if hasattr(self.client, "close"):
                await self.client.close()

def run_visualization_agent(question, sql, dataframe) -> dict | None:
    if dataframe is None or dataframe.empty:
        logger.info("[Visualization Agent]: Empty dataframe")
        return None

    if len(dataframe.columns) < 2:
        return None

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    raw = loop.run_until_complete(
        VisualizationAgent().analyze(
            question=question,
            sql=sql,
            dataframe_columns=dataframe.columns.tolist(),
            row_count=len(dataframe),
        )
    )
    loop.close()

    cleaned = raw.replace("```json", "").replace("```", "").strip()
    spec = json.loads(cleaned)

    if spec.get("visualization", "none").lower() == "none":
        return None

    if spec.get("x_axis") not in dataframe.columns or spec.get("y_axis") not in dataframe.columns:
        return None

    return spec