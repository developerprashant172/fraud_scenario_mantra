import os
import json
import time
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv

from app.models import FraudQuery, FraudResponse, CompensationQuery, CompensationResponse
from app.utils import (
    zilliz_search_async,
    zilliz_search,
    format_top_matches_for_prompt,
    lookup_bank_links,
    compute_probability_from_scores,
    shared_http_client
)
from app.llm_client import (
    get_embedding_async,
    run_llm_async,
    stream_llm_async,
    prewarm_openai_connections,
    async_client,
    LLM_MODEL,
    EMBEDDING_MODEL
)

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fraud_api")

COLLECTION = os.getenv("MILVUS_COLLECTION", "fraud_scenarios")
COMP_COLLECTION = os.getenv("COMP_COLLECTION", "bank_compensation_rules")
ZILLIZ_ENDPOINT = os.getenv("ZILLIZ_ENDPOINT")
ZILLIZ_TOKEN = os.getenv("ZILLIZ_API_KEY")


# ----------------------------------------------------
# Background Warmup on Server Startup
# ----------------------------------------------------
async def warmup_services():
    """Pre-warms DNS & TLS handshakes for OpenAI and Zilliz Cloud in the background."""
    logger.info("Pre-warming OpenAI and Zilliz Cloud connections in background...")
    try:
        # Prewarm OpenAI
        t_w = asyncio.create_task(prewarm_openai_connections())

        # Prewarm Zilliz Cloud HTTP connection
        dummy_vec = [0.01] * 1536
        t_z = asyncio.create_task(
            shared_http_client.post(
                f"{ZILLIZ_ENDPOINT}/v2/vectordb/entities/search",
                json={"collectionName": COLLECTION, "data": [dummy_vec], "limit": 1, "outputFields": ["metadata"]},
                headers={"Authorization": f"Bearer {ZILLIZ_TOKEN}", "Content-Type": "application/json"}
            )
        )
        await asyncio.gather(t_w, t_z, return_exceptions=True)
        logger.info("✅ All connections pre-warmed. Ready for low-latency traffic.")
    except Exception as e:
        logger.warning(f"Warmup notice: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: trigger warmup task without blocking server boot
    asyncio.create_task(warmup_services())
    yield
    # Shutdown: cleanly close HTTP client
    await shared_http_client.aclose()


app = FastAPI(
    title="Fraud Detection RAG API",
    version="3.0",
    description="High-Speed Fraud Detection powered by OpenAI gpt-4o-mini and Zilliz Cloud DB",
    lifespan=lifespan
)


# ----------------------------------------------------
# Endpoint: /fraud-assess (Optimized JSON Response)
# ----------------------------------------------------
@app.post("/fraud-assess", response_model=FraudResponse)
async def fraud_assess(request: FraudQuery, response: Response):
    """
    High-Performance Fraud Assessment (OpenAI + Zilliz Cloud DB):
    1. Async OpenAI Embedding (text-embedding-3-small, ~300ms)
    2. Async Zilliz Cloud Search with connection pooling (~200ms)
    3. Probability calculation (<1ms)
    4. Async OpenAI LLM generation (gpt-4o-mini, ~2.5s)
    """
    if not request.user_story.strip():
        raise HTTPException(status_code=400, detail="User story cannot be empty")

    t_total_0 = time.time()
    top_k = request.top_k or 5

    # 1. Async OpenAI Embedding (~300ms)
    t_emb_0 = time.time()
    emb = await get_embedding_async(request.user_story)
    t_emb = (time.time() - t_emb_0) * 1000

    # 2. Async Zilliz Cloud Search with keep-alive connection (~200ms)
    t_search_0 = time.time()
    results = await zilliz_search_async(COLLECTION, emb, top_k=top_k)
    t_search = (time.time() - t_search_0) * 1000

    if not results:
        raise HTTPException(404, "No similar scenarios found in Zilliz Cloud")

    # 3. Calculate true probability & format prompt context
    scores = [m.get("similarity", 0.0) for m in results]
    probability = compute_probability_from_scores(scores)
    formatted = format_top_matches_for_prompt(results)

    # 4. Async OpenAI LLM generation (gpt-4o-mini, ~2.5s)
    t_llm_0 = time.time()
    markdown = await run_llm_async(request.user_story, formatted)
    t_llm = (time.time() - t_llm_0) * 1000

    total_time = (time.time() - t_total_0) * 1000

    # Latency diagnostic headers
    response.headers["X-Embedding-Time-Ms"] = f"{t_emb:.1f}"
    response.headers["X-Search-Time-Ms"] = f"{t_search:.1f}"
    response.headers["X-LLM-Time-Ms"] = f"{t_llm:.1f}"
    response.headers["X-Total-Time-Ms"] = f"{total_time:.1f}"
    response.headers["X-Vector-DB"] = "Zilliz-Cloud"
    response.headers["X-LLM-Model"] = LLM_MODEL

    logger.info(
        f"[/fraud-assess] Total: {total_time:.1f}ms | "
        f"Embed (OpenAI): {t_emb:.1f}ms | Search (Zilliz Cloud): {t_search:.1f}ms | "
        f"LLM (OpenAI/{LLM_MODEL}): {t_llm:.1f}ms"
    )

    return FraudResponse(
        probability=probability,
        top_matches=results,
        markdown=markdown
    )


# ----------------------------------------------------
# Endpoint: /fraud-assess/stream (Live Token Streaming)
# ----------------------------------------------------
@app.post("/fraud-assess/stream")
async def fraud_assess_stream(request: FraudQuery):
    """
    Live streaming endpoint for UI (Time-to-First-Token < 800ms).
    """
    if not request.user_story.strip():
        raise HTTPException(status_code=400, detail="User story cannot be empty")

    top_k = request.top_k or 5
    emb = await get_embedding_async(request.user_story)
    results = await zilliz_search_async(COLLECTION, emb, top_k=top_k)

    if not results:
        raise HTTPException(404, "No similar scenarios found in Zilliz Cloud")

    formatted = format_top_matches_for_prompt(results)

    async def token_generator():
        async for chunk in stream_llm_async(request.user_story, formatted):
            yield chunk

    return StreamingResponse(token_generator(), media_type="text/plain")


# ----------------------------------------------------
# Compensation Engine Endpoints (Async & Parallelized)
# ----------------------------------------------------
def format_comp_rule_for_prompt(match):
    meta = match.get("metadata", {})
    return f"""
Compensation Type: {meta.get('compensation_type', '-')}
Eligibility Criteria: {meta.get('eligibility', '-')}
Calculation Method: {meta.get('calculation_method', '-')}
"""


async def run_compensation_llm_async(user_message: str, matched_rule_block: str) -> str:
    prompt = f"""You are a banking compensation eligibility engine for Indian banks.
You will receive:
(A) A user complaint message.
(B) The matched compensation policy rule.

Your tasks:
1. Extract transaction_amount from user message. If missing, return "none".
2. Extract transaction_date from user message. If missing, return "none".
3. Using the compensation rule logic provided, determine if user is eligible.
   Eligibility can be true ONLY if both amount and date are present.
4. If eligible, calculate compensation_amount strictly following the calculation method.
   If calculation not possible, return "none".
5. other_info must:
   - Summarize the case
   - Mention missing information if any
   - Explain why eligible or not

Return ONLY a valid JSON object exactly in this format:
{{
 "transaction_amount": "... or none",
 "transaction_date": "... or none",
 "compensation_eligible": true/false,
 "compensation_amount": "... or none",
 "other_info": "..."
}}
Do not return anything outside JSON.
Do not use markdown.

--------------------
User Message:
{user_message}

Matched Compensation Rule:
{matched_rule_block}
"""
    res = await async_client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    return res.choices[0].message.content


async def extract_bank_name_async(user_message: str):
    prompt = f"""Extract bank name from this message.
If no bank mentioned return "None".
Return only bank name text, nothing else.

Message:
{user_message}
"""
    res = await async_client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    name = res.choices[0].message.content.strip()
    if name.lower() == "none":
        return None
    return name


@app.post("/mantra_compensation", response_model=CompensationResponse)
async def mantra_compensation(request: CompensationQuery):
    # Step 1: Embed
    emb = await get_embedding_async(request.user_message)

    # Step 2: Vector search on Zilliz Cloud
    results = await zilliz_search_async(COMP_COLLECTION, emb, top_k=5)

    if not results:
        return {
            "transaction_amount": "none",
            "transaction_date": "none",
            "compensation_eligible": False,
            "compensation_amount": "none",
            "other_info": "No matching compensation policy found in Zilliz Cloud",
            "bank_name": None,
            "links": None
        }

    # Step 3: Top rule
    top_rule = results[0]
    rule_block = format_comp_rule_for_prompt(top_rule)

    # Step 4 & 5: Run LLM evaluation and Bank Name extraction IN PARALLEL!
    comp_task = asyncio.create_task(run_compensation_llm_async(request.user_message, rule_block))
    bank_task = asyncio.create_task(extract_bank_name_async(request.user_message))

    llm_json, bank_name = await asyncio.gather(comp_task, bank_task)

    try:
        response_data = json.loads(llm_json)
    except Exception:
        response_data = {
            "transaction_amount": "none",
            "transaction_date": "none",
            "compensation_eligible": False,
            "compensation_amount": "none",
            "other_info": llm_json
        }

    # Step 6: Lookup policy links
    links = None
    if bank_name:
        links = lookup_bank_links(bank_name)

    response_data["bank_name"] = bank_name
    response_data["links"] = links

    return response_data
