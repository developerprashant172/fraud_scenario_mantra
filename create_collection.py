import requests, os
from dotenv import load_dotenv

load_dotenv()

ZILLIZ_ENDPOINT = os.getenv("ZILLIZ_ENDPOINT")
ZILLIZ_TOKEN = os.getenv("ZILLIZ_API_KEY")

url = f"{ZILLIZ_ENDPOINT}/v2/vectordb/collections/create"

payload = {
  "collectionName": "bank_compensation_rules",
  "dimension": 1536,        # text-embedding-3-small dimension
  "metricType": "COSINE",
  "vectorField": "vector"
}

headers = {
  "Authorization": f"Bearer {ZILLIZ_TOKEN}",
  "Content-Type": "application/json"
}

r = requests.post(url, json=payload, headers=headers)
print(r.json())
