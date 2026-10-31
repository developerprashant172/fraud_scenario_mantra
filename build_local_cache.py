import os
import json
import time
import pandas as pd
from fastembed import TextEmbedding

SOURCE_PATH = "fraud_scenarios.xlsx"
CACHE_PATH = "fraud_scenarios_cache.json"

def build_cache():
    print(f"Reading {SOURCE_PATH}...")
    df = pd.read_excel(SOURCE_PATH)
    df.columns = [str(c).strip() for c in df.columns]

    records = []
    texts_to_embed = []

    for idx, row in df.iterrows():
        f_type = str(row.get("type", "")).strip()
        f_method = str(row.get("method", "")).strip()
        amount = str(row.get("Amount", "")).strip()
        pay_method = str(row.get("payment method", "")).strip()
        category = str(row.get("category", "")).strip()
        
        reached = str(row.get("how fraudster reached?", "")).strip()
        convinced = str(row.get("how convinced user?", "")).strip()
        stole = str(row.get("how stole money?", "")).strip()
        identified = str(row.get("how user identified fraud? ", "")).strip()

        summary_parts = [p for p in [reached, convinced, stole, identified] if p and p != "nan"]
        summary = " ".join(summary_parts)

        title = f"{f_type} - {f_method}" if f_method else f_type

        meta = {
            "title": title,
            "type": f_type,
            "method": f_method,
            "amount": amount,
            "payment_method": pay_method,
            "category": category,
            "summary": summary
        }

        embed_text = f"Title: {title}\nType: {f_type}\nMethod: {f_method}\nPayment Method: {pay_method}\nDetails: {summary}"
        
        records.append({
            "id": str(idx),
            "metadata": meta
        })
        texts_to_embed.append(embed_text)

    print(f"Loading fastembed local model BAAI/bge-small-en-v1.5...")
    model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")

    t0 = time.time()
    embeddings = list(model.embed(texts_to_embed))
    t1 = time.time()
    print(f"Embedded {len(embeddings)} scenarios locally in {(t1 - t0)*1000:.1f} ms!")

    for i, emb in enumerate(embeddings):
        records[i]["vector"] = emb.tolist()

    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f)

    print(f"Successfully cached {len(records)} scenarios to {CACHE_PATH}")

if __name__ == "__main__":
    build_cache()
