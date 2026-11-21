import httpx
from .config import OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_BASE_URL

SYSTEM_PROMPT = """You are Property Intelligence Assistant for DarGlobal and Wasalt.
Answer only from the supplied retrieved context. Do not invent projects, prices, availability,
locations, legal status, yields, or property details. If context is insufficient, say so clearly
and suggest opening the source page. Distinguish developer information (DarGlobal) from marketplace
listings and platform services (Wasalt). Listing prices and availability can change; tell users to
verify on the live source. Cite claims using [1], [2], etc. Use concise, helpful language."""

async def answer(question, context):
    if not OPENROUTER_API_KEY:
        return ("The knowledge base found relevant source material, but AI responses are not enabled yet. "
                "Add OPENROUTER_API_KEY in the deployment environment to enable the LLM. "
                "Relevant excerpts are shown below.")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Retrieved context:\n{context}\n\nQuestion: {question}"}
    ]
    payload = {"model": OPENROUTER_MODEL, "messages": messages, "temperature": 0.2, "max_tokens": 700}
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://property-intelligence-assistant.onrender.com",
        "X-Title": "Property Intelligence Assistant"
    }
    async with httpx.AsyncClient(timeout=55) as client:
        response = await client.post(f"{OPENROUTER_BASE_URL}/chat/completions", json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
