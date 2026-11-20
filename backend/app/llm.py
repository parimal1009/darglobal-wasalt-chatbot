from typing import Iterator

from openai import OpenAI

from .config import settings

SYSTEM_PROMPT = """You are the assistant for Dar Global (luxury real-estate developer) and Wasalt (Saudi real-estate marketplace).
Answer ONLY using the CONTEXT excerpts provided. If the context does not contain the answer, say you don't have that information in the collected data and suggest visiting the official websites. Never invent prices, locations or facts.
Be concise and well formatted. Mention the company (Dar Global or Wasalt) each fact refers to."""


def build_messages(question: str, history: list[dict], contexts: list[dict]) -> list[dict]:
    ctx = "\n\n".join(
        f"[{i + 1}] ({c['source']}) {c['title']} - {c['url']}\n{c['content']}" for i, c in enumerate(contexts)
    ) or "(no relevant context found)"
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    msgs += [m for m in history[-6:] if m.get("role") in ("user", "assistant")]
    msgs.append({"role": "user", "content": f"CONTEXT:\n{ctx}\n\nQUESTION: {question}"})
    return msgs


def _client() -> OpenAI:
    return OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key, timeout=60)


def stream_answer(messages: list[dict]) -> Iterator[str]:
    stream = _client().chat.completions.create(
        model=settings.llm_model, messages=messages, stream=True, temperature=0.2, max_tokens=1024
    )
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
