
import httpx

from .config import (
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    OPENROUTER_BASE_URL,
)


SYSTEM_PROMPT = """
You are the Property Intelligence Assistant for DarGlobal and Wasalt.

Your job is to answer questions using ONLY the retrieved context.

STRICT RULES:

1. Never invent property details, prices, availability, projects,
   locations, legal status, investment returns, or services.

2. Clearly distinguish:
   - DarGlobal: real estate developer and property projects.
   - Wasalt: Saudi Arabian real estate marketplace and platform.

3. Answer the user's actual question directly.

4. Write complete sentences. Never return an unfinished sentence,
   isolated word, or incomplete response.

5. If the context contains the answer, explain it clearly.
   Do not unnecessarily say information is unavailable.

6. If the context is insufficient, explain what information
   is missing and suggest checking the original source.

7. Cite relevant sources using [1], [2], etc.

8. For property prices and availability, remind users to
   verify information on the live source.

9. Keep answers helpful and concise.

10. Never fabricate citations or source information.
"""


def extract_content(message):
    """Extract text from different OpenRouter response formats."""

    content = message.get("content")

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts = []

        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))

        return "\n".join(parts).strip()

    return ""


async def call_openrouter(messages, max_tokens=900):
    """Make a request to OpenRouter and validate its response."""

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": (
            "https://darglobal-wasalt-ai-chatbot-aa1h.onrender.com"
        ),
        "X-Title": "DarGlobal Wasalt Property Assistant",
    }

    async with httpx.AsyncClient(timeout=90) as client:

        response = await client.post(
            f"{OPENROUTER_BASE_URL.rstrip('/')}/chat/completions",
            json=payload,
            headers=headers,
        )

        response.raise_for_status()

        data = response.json()

    choices = data.get("choices", [])

    if not choices:
        raise RuntimeError(
            f"OpenRouter returned no choices: {data}"
        )

    choice = choices[0]
    message = choice.get("message", {})

    answer_text = extract_content(message)

    if not answer_text:
        raise RuntimeError(
            "OpenRouter returned an empty response."
        )

    return answer_text, choice.get("finish_reason")


async def answer(question, context):
    """Generate an answer grounded in retrieved documents."""

    if not OPENROUTER_API_KEY:
        return (
            "Relevant documents were found, but AI responses "
            "are not enabled. Configure OPENROUTER_API_KEY "
            "in your deployment environment."
        )

    user_prompt = f"""
RETRIEVED KNOWLEDGE:

{context}

USER QUESTION:
{question}

INSTRUCTIONS:

Answer the question using the retrieved knowledge above.

If the question asks about a Wasalt service, explain the relevant
service using the supplied context.

If the question asks for a comparison, explain both platforms
separately and then compare their business models.

Use complete sentences and relevant source citations.

Do not return an unfinished answer.
"""

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": user_prompt,
        },
    ]

    try:

        # First attempt
        response_text, finish_reason = await call_openrouter(
            messages,
            max_tokens=900,
        )

        # Detect suspiciously short or incomplete responses.
        incomplete = (
            len(response_text.strip()) < 25
            or finish_reason == "length"
        )

        if incomplete:

            print(
                "Incomplete OpenRouter response detected. Retrying..."
            )

            retry_messages = messages + [
                {
                    "role": "assistant",
                    "content": response_text,
                },
                {
                    "role": "user",
                    "content": (
                        "Your previous response was incomplete. "
                        "Please provide a complete, helpful answer "
                        "to the original question using the "
                        "retrieved context. Write full sentences "
                        "and include source citations."
                    ),
                },
            ]

            retry_text, retry_reason = await call_openrouter(
                retry_messages,
                max_tokens=1200,
            )

            if (
                len(retry_text.strip()) >= 25
                and retry_reason != "length"
            ):
                return retry_text

            if len(response_text.strip()) >= 25:
                return response_text

            return (
                "I found relevant information, but the AI provider "
                "returned an incomplete answer. Please try again."
            )

        return response_text

    except httpx.HTTPStatusError as exc:

        error_body = exc.response.text[:500]

        print(
            f"OpenRouter HTTP error: "
            f"{exc.response.status_code}: {error_body}"
        )

        raise RuntimeError(
            f"OpenRouter returned HTTP {exc.response.status_code}"
        ) from exc

    except httpx.RequestError as exc:

        print(f"OpenRouter connection error: {exc}")

        raise RuntimeError(
            "Could not connect to OpenRouter."
        ) from exc
