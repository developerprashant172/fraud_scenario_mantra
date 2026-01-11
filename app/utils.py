# app/utils.py
import os
import json
import math
import requests
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

# Zilliz (Milvus Cloud) REST settings
ZILLIZ_ENDPOINT = os.getenv("ZILLIZ_ENDPOINT")  # e.g. https://in-xxxxx.aws-region.zillizcloud.com
ZILLIZ_TOKEN = os.getenv("ZILLIZ_API_KEY")
ZILLIZ_COLLECTION = os.getenv("MILVUS_COLLECTION", "fraud_scenarios")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set in .env")

client = OpenAI(api_key=OPENAI_API_KEY)


def get_embedding(text: str):
    """Return embedding vector for the given text using OpenAI embeddings API."""
    resp = client.embeddings.create(model=EMBED_MODEL, input=text)
    emb = resp.data[0].embedding
    return emb


def zilliz_insert_vectors(collection: str, ids: list, vectors: list, metadatas: list):
    """
    Insert vectors into Zilliz Cloud via REST.
    The exact REST contract can differ slightly by Zilliz version - this is a commonly supported shape.
    """
    if not ZILLIZ_ENDPOINT or not ZILLIZ_TOKEN:
        raise RuntimeError("ZILLIZ_ENDPOINT and ZILLIZ_API_KEY must be set in .env")

    url = f"{ZILLIZ_ENDPOINT}/v2/vectordb/entities/insert"

    headers = {
        "Authorization": f"Bearer {ZILLIZ_TOKEN}",
        "Content-Type": "application/json"
    }
    # Each "data" item may include id, vector, metadata
    data = {
        "collectionName": collection,
        "data": []
    }
    for i in range(len(ids)):
        data["data"].append({
            "id": str(ids[i]),
            "vector": vectors[i],
            "metadata": metadatas[i]
        })
    r = requests.post(url, headers=headers, json=data, timeout=60)
    r.raise_for_status()
    return r.json()


def zilliz_search(collection_name, vector, top_k=5):
    """
    Zilliz Serverless Search (Confirmed Response Format)
    Expected response:
    {
      "code": 0,
      "data": [
        { "distance": 0.01, "id": 12, "metadata": {...}, "vector": [...] }
      ]
    }
    """

    url = f"{ZILLIZ_ENDPOINT}/v2/vectordb/entities/search"

    payload = {
        "collectionName": collection_name,
        "data": [vector],           # list of embeddings
        "limit": top_k,
        "outputFields": ["*"]       # return metadata
    }

    headers = {
        "Authorization": f"Bearer {ZILLIZ_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    r = requests.post(url, json=payload, headers=headers)

    if r.status_code != 200:
        raise Exception(f"Search failed: {r.text}")

    res = r.json()

    # ---- exact format you confirmed ----
    if "data" in res and isinstance(res["data"], list):
        formatted = []
        for item in res["data"]:
            distance = float(item.get("distance", 0))
            similarity = 1 - distance     # convert distance → similarity (0 to 1)

            formatted.append({
                "id": str(item.get("id")),
                "similarity": round(similarity, 4),
                "metadata": item.get("metadata", {})
            })

        return formatted

    # ---- fallback: unknown format ----
    return {"raw_response": res}





def format_top_matches_for_prompt(matches):
    parts = []
    for i, m in enumerate(matches, 1):
        meta = m.get("metadata", {})
        title = meta.get("title") or meta.get("summary") or meta.get("type") or f"scenario_{m.get('id')}"
        typ = meta.get("type", "-")
        method = meta.get("method", "-")
        summary = meta.get("summary", "-")
        part = f"## Scenario {i}\n- id: {m.get('id')}\n- title: {title}\n- type: {typ}\n- method: {method}\n- summary: {summary}\n- similarity: {round(float(m.get('score', m.get('similarity', 0))), 4)}"
        parts.append(part)
    return "\n\n".join(parts)


def compute_probability_from_scores(scores):
    """
    Convert similarity scores to a 0..1 probability.
    Assumes scores are similarity-like (higher = better). If score looks like distance, convert outside.
    We'll map mean score within typical range to [0,1].
    """
    if not scores:
        return 0.0
    mean = sum(scores) / len(scores)
    # clamp sensible range: treat mean <0.4 as low, >0.9 as high
    prob = (mean - 0.4) / (0.95 - 0.4)
    prob = max(0.0, min(1.0, prob))
    return round(prob, 2)


def call_openai_summarize(user_story: str, top_matches_context: str, probability: float):
    prompt = f"""
You are an expert Indian banking fraud analyst. A user described this incident:

User story:
{user_story}

Top matching known scenarios (short summaries):
{top_matches_context}

Prior probability (0..1): {probability}

Produce a **detailed Markdown** report containing:
- One-line summary with the estimated probability as percent.
- For each matched scenario: why it's relevant (1-2 lines).
- What likely happened in plain language.
- Immediate actions user must take (freeze, dispute, contacts).
- Evidence checklist (what to collect).
- Where to escalate (bank grievance, RBI Ombudsman).
- Confidence & limitations.

Use ₹ for currency. Keep it actionable and polite.
"""
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful, precise banking fraud assistant who outputs Markdown."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
        max_tokens=1200
    )
    text = resp.choices[0].message.content
    return text


def zilliz_search_compensation(collection, query_vector, top_k=5):
    url = f"{ZILLIZ_ENDPOINT}/v2/vectordb/entities/search"

    payload = {
        "collectionName": collection,
        "data": [query_vector],
        "limit": top_k,
        "outputFields": ["*"]
    }

    headers = {
        "Authorization": f"Bearer {ZILLIZ_TOKEN}",
        "Content-Type": "application/json"
    }

    r = requests.post(url, json=payload, headers=headers)
    r.raise_for_status()

    res = r.json()
    return res["data"]

import re

def calculate_compensation(calc_text: str, user_text: str):
    """
    Very simple rule engine using regex.
    Extendable later.
    """

    calc_text = calc_text.lower()

    # Rule: ₹100 per day delay
    m = re.search(r"₹?100 per day", calc_text)
    if m:
        # Try extract days from user query
        days = re.search(r"(\d+)\s*day", user_text.lower())
        d = int(days.group(1)) if days else 1
        return d * 100, "₹100 per day of delay"

    # Rule: reverse full amount
    if "full reversal" in calc_text or "full refund" in calc_text:
        amt = re.search(r"₹\s?([\d,]+)", user_text)
        if amt:
            amount = int(amt.group(1).replace(",", ""))
            return amount, "Full amount refundable"
        return None, "Full refund applicable"

    # Rule: fixed ₹100 compensation
    if "₹100" in calc_text:
        return 100, "Fixed ₹100 compensation"

    # fallback
    return None, "Refer to bank for exact calculation"


