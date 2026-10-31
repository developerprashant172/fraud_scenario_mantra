# app/utils.py
import os
import json
import math
import requests
import httpx
import re
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

# Zilliz (Milvus Cloud) REST settings
ZILLIZ_ENDPOINT = os.getenv("ZILLIZ_ENDPOINT")
ZILLIZ_TOKEN = os.getenv("ZILLIZ_API_KEY")
ZILLIZ_COLLECTION = os.getenv("MILVUS_COLLECTION", "fraud_scenarios")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set in .env")

client = OpenAI(api_key=OPENAI_API_KEY)

# Shared high-performance HTTP client with persistent connection pooling
shared_http_client = httpx.AsyncClient(
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=50, keepalive_expiry=60.0),
    timeout=httpx.Timeout(10.0, connect=3.0)
)


def get_embedding(text: str):
    """Return embedding vector for the given text using OpenAI embeddings API."""
    resp = client.embeddings.create(model=EMBED_MODEL, input=text)
    return resp.data[0].embedding


def zilliz_insert_vectors(collection: str, ids: list, vectors: list, metadatas: list):
    """Insert vectors into Zilliz Cloud via REST."""
    if not ZILLIZ_ENDPOINT or not ZILLIZ_TOKEN:
        raise RuntimeError("ZILLIZ_ENDPOINT and ZILLIZ_API_KEY must be set in .env")

    url = f"{ZILLIZ_ENDPOINT}/v2/vectordb/entities/insert"
    headers = {
        "Authorization": f"Bearer {ZILLIZ_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {"collectionName": collection, "data": []}
    for i in range(len(ids)):
        data["data"].append({
            "id": str(ids[i]),
            "vector": vectors[i],
            "metadata": metadatas[i]
        })
    r = requests.post(url, headers=headers, json=data, timeout=60)
    r.raise_for_status()
    return r.json()


async def zilliz_search_async(collection_name: str, vector: list, top_k: int = 5):
    """
    High-performance Async Zilliz Cloud Search.
    Uses connection pooling and requests only metadata (skipping 1536 float vectors for lower bandwidth).
    """
    url = f"{ZILLIZ_ENDPOINT}/v2/vectordb/entities/search"
    payload = {
        "collectionName": collection_name,
        "data": [vector],
        "limit": top_k,
        "outputFields": ["metadata"]
    }
    headers = {
        "Authorization": f"Bearer {ZILLIZ_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    try:
        r = await shared_http_client.post(url, json=payload, headers=headers)
        if r.status_code != 200:
            # Fallback if outputFields doesn't support selective field on custom collection
            payload["outputFields"] = ["*"]
            r = await shared_http_client.post(url, json=payload, headers=headers)
            if r.status_code != 200:
                raise Exception(f"Zilliz search failed: {r.text}")

        res = r.json()
        if "data" in res and isinstance(res["data"], list):
            formatted = []
            for item in res["data"]:
                distance = float(item.get("distance", 0))
                similarity = 1 - distance
                formatted.append({
                    "id": str(item.get("id")),
                    "similarity": round(similarity, 4),
                    "metadata": item.get("metadata", {})
                })
            return formatted
        return []
    except Exception as e:
        raise Exception(f"Async Zilliz search error: {e}")


def zilliz_search(collection_name, vector, top_k=5):
    """Synchronous fallback for legacy callers."""
    url = f"{ZILLIZ_ENDPOINT}/v2/vectordb/entities/search"
    payload = {
        "collectionName": collection_name,
        "data": [vector],
        "limit": top_k,
        "outputFields": ["metadata"]
    }
    headers = {
        "Authorization": f"Bearer {ZILLIZ_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    r = requests.post(url, json=payload, headers=headers)
    if r.status_code != 200:
        payload["outputFields"] = ["*"]
        r = requests.post(url, json=payload, headers=headers)
        if r.status_code != 200:
            raise Exception(f"Search failed: {r.text}")

    res = r.json()
    if "data" in res and isinstance(res["data"], list):
        formatted = []
        for item in res["data"]:
            distance = float(item.get("distance", 0))
            similarity = 1 - distance
            formatted.append({
                "id": str(item.get("id")),
                "similarity": round(similarity, 4),
                "metadata": item.get("metadata", {})
            })
        return formatted
    return []


def format_top_matches_for_prompt(matches):
    parts = []
    for i, m in enumerate(matches, 1):
        meta = m.get("metadata", {})
        title = meta.get("title") or meta.get("summary") or meta.get("type") or f"scenario_{m.get('id')}"
        typ = meta.get("type", "-")
        method = meta.get("method", "-")
        summary = meta.get("summary", "-")
        score = round(float(m.get("similarity", m.get("score", 0))), 4)
        parts.append(f"## Scenario {i}\n- title: {title}\n- type: {typ}\n- method: {method}\n- summary: {summary}\n- similarity: {score}")
    return "\n\n".join(parts)


def compute_probability_from_scores(scores):
    """Convert similarity scores to a 0..1 probability."""
    if not scores:
        return 0.0
    mean = sum(scores) / len(scores)
    prob = (mean - 0.4) / (0.95 - 0.4)
    prob = max(0.0, min(1.0, prob))
    return round(prob, 2)


def zilliz_search_compensation(collection, query_vector, top_k=5):
    return zilliz_search(collection, query_vector, top_k=top_k)


def calculate_compensation(calc_text: str, user_text: str):
    calc_text = calc_text.lower()
    m = re.search(r"₹?100 per day", calc_text)
    if m:
        days = re.search(r"(\d+)\s*day", user_text.lower())
        d = int(days.group(1)) if days else 1
        return d * 100, "₹100 per day of delay"

    if "full reversal" in calc_text or "full refund" in calc_text:
        amt = re.search(r"₹\s?([\d,]+)", user_text)
        if amt:
            amount = int(amt.group(1).replace(",", ""))
            return amount, "Full amount refundable"
        return None, "Full refund applicable"

    if "₹100" in calc_text:
        return 100, "Fixed ₹100 compensation"

    return None, "Refer to bank for exact calculation"


BANK_POLICY_PATH = "bank_policy.csv"
if os.path.exists(BANK_POLICY_PATH):
    BANK_POLICY_DF = pd.read_csv(BANK_POLICY_PATH)
    BANK_POLICY_DF["Bank Name"] = BANK_POLICY_DF["Bank Name"].str.lower().str.strip()
else:
    BANK_POLICY_DF = None


def lookup_bank_links(bank_name: str):
    if BANK_POLICY_DF is None or not bank_name:
        return None
    
    BANK_POLICY_DF["Bank Name Clean"] = (
        BANK_POLICY_DF["Bank Name"]
        .astype(str)
        .str.lower()
        .str.strip()
    )
    name_clean = bank_name.lower().strip()
    row = BANK_POLICY_DF[BANK_POLICY_DF["Bank Name Clean"].str.contains(name_clean)]
    if row.empty:
        return None
    r = row.iloc[0]
    return {
        "compensation_policy": r.get("Compensataion Policy Link", None),
        "grievance_policy": r.get("Grievance redressal policy", None)
    }
