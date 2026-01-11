# indexer.py  (UTF-8 compatible)

import os
import time
import json
import pandas as pd
import requests
from dotenv import load_dotenv
from app.utils import get_embedding, ZILLIZ_COLLECTION

load_dotenv()

ZILLIZ_API_KEY = os.getenv("ZILLIZ_API_KEY")
ZILLIZ_BASE_URL = os.getenv("ZILLIZ_ENDPOINT")  

CREATE_URL = f"{ZILLIZ_BASE_URL}/v2/vectordb/collections/create"
INSERT_URL = f"{ZILLIZ_BASE_URL}/v2/vectordb/entities/insert"

SOURCE_PATH = "fraud_scenarios.xlsx"
COLLECTION = os.getenv("ZILLIZ_COLLECTION", ZILLIZ_COLLECTION)
BATCH_SIZE = int(os.getenv("INDEX_BATCH", 50))

headers = {
    "Authorization": f"Bearer {ZILLIZ_API_KEY}",
    "Accept": "application/json",
    "Content-Type": "application/json"
}


# ---------------------------------------------------------
# 1️⃣ Create Collection if not exists
# ---------------------------------------------------------
def create_collection_if_needed():
    print(f"\n📌 Checking/Creating collection: {COLLECTION}")

    payload = {
        "collectionName": COLLECTION,
        "dimension": 1536,          # OpenAI text-embedding-3-large
        "metricType": "COSINE",
        "vectorField": "vector"
    }

    try:
        res = requests.post(CREATE_URL, headers=headers, data=json.dumps(payload))
        print("➡️ Create collection response:", res.json())
    except Exception as e:
        print("❌ Error creating collection:", e)


# ---------------------------------------------------------
# 2️⃣ Load Excel dataset
# ---------------------------------------------------------
def load_data():
    if not os.path.exists(SOURCE_PATH):
        raise FileNotFoundError(f"Source Excel not found: {SOURCE_PATH}")

    print("\n📖 Reading spreadsheet:", SOURCE_PATH)
    df = pd.read_excel(SOURCE_PATH)
    df.columns = [str(c).strip() for c in df.columns]
    print("✅ Rows loaded:", len(df))
    return df


# ---------------------------------------------------------
# 3️⃣ Format metadata from row
# ---------------------------------------------------------
def build_metadata(row, df, idx):
    title = row.get('Keyword', f"scenario_{idx}")
    typ = row.get('Charge Type', "")

    summary_parts = []
    for key in ['Category', 'summary', 'how stole money?', 'how user identified fraud?', 'notes', 'description']:
        if key in df.columns:
            val = row.get(key, "")
            if pd.notna(val) and str(val).strip():
                summary_parts.append(str(val).strip())

    summary = " ".join(summary_parts)[:800]

    return title, typ, summary, f"Title: {title}\nType: {typ}\nSummary: {summary}"


# ---------------------------------------------------------
# 4️⃣ Batch Insert into Zilliz
# ---------------------------------------------------------
def zilliz_insert_batch(collection_name, ids, vectors, metadatas):
    records = []
    for i, emb in enumerate(vectors):
        records.append({
            "id": ids[i],
            "vector": emb,
            "metadata": metadatas[i]
        })

    payload = {
        "collectionName": collection_name,
        "data": records
    }

    res = requests.post(INSERT_URL, headers=headers, data=json.dumps(payload))
    try:
        return res.json()
    except:
        return {"error": "Invalid JSON response", "raw": res.text}


# ---------------------------------------------------------
# MAIN INDEXING FUNCTION
# ---------------------------------------------------------
def run_indexing():
    create_collection_if_needed()

    df = load_data()

    ids, vectors, metadatas = [], [], []

    print("\n⚙️ Generating embeddings and preparing data...")
    for idx, row in df.iterrows():
        title, typ, summary, doc_text = build_metadata(row, df, idx)

        try:
            emb = get_embedding(doc_text)
        except Exception as e:
            print(f"❌ Embedding failed for row {idx}: {e}")
            continue

        ids.append(int(idx))
        vectors.append(emb)
        metadatas.append({
            "title": title,
            "type": typ,
            "summary": summary
        })

    print(f"\n📦 Ready to insert {len(ids)} vectors into '{COLLECTION}'")

    for i in range(0, len(ids), BATCH_SIZE):
        batch_ids = ids[i:i+BATCH_SIZE]
        batch_vecs = vectors[i:i+BATCH_SIZE]
        batch_meta = metadatas[i:i+BATCH_SIZE]

        print(f"\n➡️ Inserting batch {i} - {i+len(batch_ids)}...")
        res = zilliz_insert_batch(COLLECTION, batch_ids, batch_vecs, batch_meta)
        print("Response:", res)
        time.sleep(0.2)

    print("\n🎉 Indexing complete!")


# ---------------------------------------------------------
# Entry Point
# ---------------------------------------------------------
if __name__ == "__main__":
    run_indexing()
