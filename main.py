import os
from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv
from openai import OpenAI
from app.models import FraudQuery, FraudResponse
from app.utils import get_embedding, zilliz_search, format_top_matches_for_prompt

load_dotenv()

app = FastAPI(title="Fraud Detection RAG API", version="1.0")

ZILLIZ_ENDPOINT = os.getenv("ZILLIZ_ENDPOINT")
ZILLIZ_TOKEN = os.getenv("ZILLIZ_API_KEY")
COLLECTION = os.getenv("MILVUS_COLLECTION", "fraud_scenarios")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)


# ------------------------------
#        LLM Wrapper
# ------------------------------
def run_llm(user_query, similar_blocks):
    prompt = f"""
You are an expert Indian digital payment fraud analyst.

Your task:
1. Carefully read the user's fraud story.
2. Carefully read ALL retrieved similar scenarios.
3. Analyse and compare similarities.
4. Then generate a COMPLETE markdown report in the structure described below.
5. At the end, mention the MOST similar scenario detected.

---

## 🧾 User Query:
{user_query}

---

## 🔍 Retrieved Similar Scenarios (Top K):
{similar_blocks}

---

## 📝 REQUIRED OUTPUT FORMAT (MANDATORY)

Produce the final answer ONLY in **Markdown**, following this exact structure:

### 🔥 Fraud Probability (0–100%)
Estimate based on similarity + narrative.

### 🏷 Most Likely Fraud Type
Pick the most suitable category based on all scenarios.

### 🧩 Matching Scenario
Name the closest matching fraud pattern.

### 🤖 Reasoning
Explain clearly why you concluded this.

### 🛠 Action Plan
Bullet list of steps user must take immediately.

### 📄 Evidence Collection
What user must gather (screenshots, SMS, timestamps, ID proof, bank statements, etc.)

### 🚨 Cybercrime Reporting Steps
Explain how to file on cybercrime.gov.in + timeline.

### 🏦 Bank Dispute Steps
Explain how to raise complaint, escalation path, nodal officer, and RBI Ombudsman.

### 🛡 Safety Checklist
Preventive steps to avoid recurrence.

---

## 🧪 MOST SIMILAR SCENARIO (MANDATORY)
At the end of the report, add:

**“There has been a similar scenario in which: <WRITE TOP MATCH TITLE HERE>”**

Where the top match is simply the first scenario from the retrieved list.

---

Keep the language:
- Simple for Indian consumers
- Accurate
- Actionable
- Fully in Markdown
"""

    res = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )

    return res.choices[0].message.content



# ------------------------------
#          ENDPOINT
# ------------------------------
@app.post("/fraud-assess", response_model=FraudResponse)
async def fraud_assess(request: FraudQuery):

    if not request.user_story.strip():
        raise HTTPException(status_code=400, detail="User story cannot be empty")

    top_k = request.top_k or 5

    # 1. Embed
    emb = get_embedding(request.user_story)

    # 2. Search Zilliz
    results = zilliz_search(COLLECTION, emb, top_k=top_k)

    if not results:
        raise HTTPException(404, "No similar scenarios found")

    # 3. Prepare for LLM
    formatted = format_top_matches_for_prompt(results)

    # 4. Run LLM
    markdown = run_llm(request.user_story, formatted)

    # 5. Return Response
    return FraudResponse(
        probability=0,  # optional: calculate later
        top_matches=results,
        markdown=markdown
    )
