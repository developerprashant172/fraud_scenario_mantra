import os
import pandas as pd
import time
from dotenv import load_dotenv
from app.utils import get_embedding, zilliz_insert_vectors

load_dotenv()

SOURCE_PATH = "Bank_Compensation_Policy_Guide.xlsx"
COLLECTION = os.getenv("COMP_COLLECTION", "bank_compensation_rules")

print("Reading Compensation Excel...")
df = pd.read_excel(SOURCE_PATH)
df.columns = [c.strip() for c in df.columns]

ids = []
vectors = []
metadatas = []

for idx, row in df.iterrows():
    comp_type = str(row["Compensation Type"])
    eligibility = str(row["Eligibility Criteria"])
    calc_method = str(row["Calculation Method"])
    example = str(row["Example"])
    exceptions = str(row["Exceptions"])

    # Build text for embedding
    doc_text = f"""
    Compensation Type: {comp_type}
    Eligibility: {eligibility}
    Calculation: {calc_method}
    Exceptions: {exceptions}
    """

    emb = get_embedding(doc_text)

    ids.append(str(idx))
    vectors.append(emb)
    metadatas.append({
        "compensation_type": comp_type,
        "eligibility": eligibility,
        "calculation_method": calc_method,
        "example": example,
        "exceptions": exceptions
    })

print("Uploading compensation vectors to Zilliz...")

zilliz_insert_vectors(COLLECTION, ids, vectors, metadatas)

print("✅ Compensation indexing complete")
