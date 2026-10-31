import os
import time
import logging
import asyncio
from typing import AsyncGenerator
import httpx
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY must be set in .env")

# High-performance shared HTTP client with persistent connection pool & keep-alive
shared_openai_http_client = httpx.AsyncClient(
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=50, keepalive_expiry=60.0),
    timeout=httpx.Timeout(15.0, connect=3.0)
)

async_client = AsyncOpenAI(
    api_key=OPENAI_API_KEY,
    http_client=shared_openai_http_client
)


async def get_embedding_async(text: str) -> list:
    """Non-blocking async text embedding with persistent keep-alive connection."""
    resp = await async_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text
    )
    return resp.data[0].embedding


def build_fraud_prompt(user_query: str, similar_blocks: str) -> str:
    return f"""You are an expert Indian digital payment fraud analyst.

Task:
Analyse the user's fraud report against the retrieved known scenarios from Zilliz Cloud, and generate a concise, structured Markdown report.

Guidelines:
- Be direct, highly actionable, and precise.
- Use concise bullet points for action steps.
- Avoid conversational fluff or introductory essays.
- Follow the exact markdown headings below.

---

## 🧾 User Query:
{user_query}

---

## 🔍 Retrieved Similar Scenarios:
{similar_blocks}

---

## 📝 REQUIRED OUTPUT FORMAT (MANDATORY)

Produce the answer ONLY in **Markdown**, following this exact structure:

### 🔥 Fraud Probability (0–100%)
State percentage and 1-line summary.

### 🏷 Most Likely Fraud Type
Category based on scenarios.

### 🧩 Matching Scenario
Name the closest pattern.

### 🤖 Reasoning
2-3 bullet points explaining why.

### 🛠 Action Plan
3 immediate steps (freeze card/UPI, alert bank, file dispute).

### 📄 Evidence Collection
What to save (SMS screenshots, UTR/Ref number, call logs).

### 🚨 Cybercrime Reporting Steps
Helpline 1930 (Golden Hour) & cybercrime.gov.in complaint steps.

### 🏦 Bank Dispute Steps
Dispute turnaround, Nodal Officer, and RBI Banking Ombudsman.

### 🛡 Safety Checklist
2 preventive rules.

---

## 🧪 MOST SIMILAR SCENARIO (MANDATORY)
**“There has been a similar scenario in which: <WRITE TOP MATCH TITLE HERE>”**
"""


async def run_llm_async(user_query: str, similar_blocks: str) -> str:
    """Non-blocking async chat completion with gpt-4o-mini."""
    prompt = build_fraud_prompt(user_query, similar_blocks)

    res = await async_client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=450
    )
    return res.choices[0].message.content


async def stream_llm_async(user_query: str, similar_blocks: str) -> AsyncGenerator[str, None]:
    """Async token stream for Server-Sent Events (SSE) live typing."""
    prompt = build_fraud_prompt(user_query, similar_blocks)

    stream = await async_client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=450,
        stream=True
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            yield delta


async def prewarm_openai_connections():
    """Warms up TLS handshake and HTTP/2 connections on startup."""
    try:
        await asyncio.gather(
            async_client.embeddings.create(model=EMBEDDING_MODEL, input="ping"),
            async_client.chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": "1"}],
                max_tokens=1
            )
        )
        logger.info("OpenAI connection pool successfully pre-warmed.")
    except Exception as e:
        logger.warning(f"OpenAI prewarm notice: {e}")
