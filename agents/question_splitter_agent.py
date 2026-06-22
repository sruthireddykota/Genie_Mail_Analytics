import asyncio
import json
import re
from agent_framework import Agent, Message, Content
from azure_clients.azure_client import get_client
from utils.logger import get_logger

logger=get_logger()

DOMAIN_MAP = {
    "Sales":  "Sales",
    "Sale": "Sales",
    "Franchise": "Franchise",
    "Franchises": "Franchise",
    "Customer": "Customer",
    "Customers": "Customer",
    "Misc": "Miscellaneous",
    "Miscellaneous": "Miscellaneous",
}

DOMAIN_KEYWORDS = {
    "Sales": ["sales", "revenue", "product", "price", "orders", "purchases",
                  "transactions", "amount", "total sales", "highest sales", "profit"],
    "Franchise": ["franchise", "franchises", "branch", "location", "store",
                  "outlet", "region", "country", "branches"],
    "Customer":  ["customer", "customers", "client", "clients", "user",
                  "name", "contact", "buyer", "buyers"],
}

MISC_PATTERNS = [
    r"^(hi|hello|hey|good\s*(morning|afternoon|evening|night))[^a-z]*$",
    r"^how are you",
    r"^(thanks|thank you|thx|ty)[^a-z]*$",
    r"^(bye|goodbye|see you|take care)[^a-z]*$",
    r"^(ok|okay|sure|got it|noted)[^a-z]*$",
]


def is_miscellaneous(question: str) -> bool:
    """Returns True if the question is a greeting, pleasantry, or clearly off-topic."""
    q = question.lower().strip()
    for pattern in MISC_PATTERNS:
        if re.match(pattern, q):
            return True
    return False


def extract_inline_domain(question: str) -> tuple[str, str | None]:

    match = re.search(r'\((\w+)\)\s*$', question.strip())
    if match:
        raw = match.group(1)
        domain = DOMAIN_MAP.get(raw.capitalize()) or DOMAIN_MAP.get(raw)
        if domain:
            clean_q = question[:match.start()].strip().rstrip("?").strip() + "?"
            return clean_q, domain
    return question, None


def keyword_classify(question: str) -> str | None:
    q_lower = question.lower()
    scores  = {domain: 0 for domain in DOMAIN_KEYWORDS}

    for domain, keywords in DOMAIN_KEYWORDS.items():
        for keyword in keywords:
            if keyword in q_lower:
                scores[domain] += 1

    best_domain = max(scores, key=scores.get)
    return best_domain if scores[best_domain] > 0 else None


class QuestionSplitterAgent:

    def __init__(self):
        self.client = get_client()

    async def split(self, email_body: str, domain_hint: str = None) -> str:
        try:
            domain_instruction = (
                f"The user has indicated the domain is '{domain_hint}' in their subject. "
                f"Assign ALL questions to '{domain_hint}' unless clearly otherwise."
                if domain_hint
                else (
                    "Assign the most relevant domain to each question using these rules:\n"
                    "- Sales: questions about revenue, products, prices, orders, transactions, amounts\n"
                    "- Franchise: questions about branches, locations, stores, regions, countries\n"
                    "- Customer: questions about customer names, contacts, buyers, clients\n"
                    "- Miscellaneous: greetings, pleasantries, unrelated questions, or anything that "
                    "does not fit Sales, Franchise, or Customer\n"
                    "Never force a question into Sales/Franchise/Customer if it clearly does not belong."
                )
            )

            prompt = f"""
You are an email analysis agent.

Your job:
1. Read the email body below
2. Split it into individual questions or requests
3. Assign a domain to each question
4. Return ONLY valid JSON — no markdown, no explanation

Available domains:
- Sales
- Franchise
- Customer
- Miscellaneous

Email body:
{email_body}

Rules:
- If a sentence is a question or request, treat it as one item
- If the email has only one question, return a list with one item
- Greetings like "Hi", "Hello", "How are you", "Thanks" must be labeled Miscellaneous
- Questions unrelated to sales data, franchise locations, or customer info must be Miscellaneous
- {domain_instruction}

Return format (JSON array):
[
  {{"question": "...", "domain": "..."}},
  {{"question": "...", "domain": "..."}}
]
"""

            message = Message(
                role="user",
                contents=[Content.from_text(prompt)]
            )

            agent = Agent(
                client=self.client,
                instructions="You are a question splitter. Return ONLY valid JSON. No markdown. No explanation."
            )

            response = ""
            async for event in agent.run(message, stream=True):
                if hasattr(event, "text") and event.text:
                    response += event.text

            return response

        finally:
            if hasattr(self.client, "close"):
                await self.client.close()


def run_question_splitter(email_body: str, domain_hint: str = None) -> list[dict]:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    raw = loop.run_until_complete(
        QuestionSplitterAgent().split(email_body, domain_hint=domain_hint)
    )
    loop.close()

    cleaned = raw.replace("```json", "").replace("```", "").strip()
    result  = json.loads(cleaned)

    final = []
    for item in result:
        question = item["question"]
        llm_domain = item["domain"]

        if is_miscellaneous(question):
            final.append({"question": question, "domain": "Miscellaneous"})
            continue

        clean_q, inline_domain = extract_inline_domain(question)
        if inline_domain:
            final.append({"question": clean_q, "domain": inline_domain})
            continue

        keyword_domain = keyword_classify(clean_q)
        if keyword_domain:
            final.append({"question": clean_q, "domain": keyword_domain})
            continue

        domain = llm_domain if llm_domain in ("Sales", "Franchise", "Customer") else "Miscellaneous"
        final.append({"question": clean_q, "domain": domain})

    logger.info(f"[Question Splitter]: {len(final)} questions found")

    return final