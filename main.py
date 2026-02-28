import os
import json
from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv
from openai import OpenAI
from app.models import FraudQuery, FraudResponse, CompensationQuery, CompensationResponse
from app.utils import get_embedding, zilliz_search, format_top_matches_for_prompt, lookup_bank_links
from app.compensation_formulas import dispatch_compensation
##uvicorn main:app --reload
##pip install -r requirements.txt
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


def format_comp_rule_for_prompt(match):
    meta = match["metadata"]
    return f"""
Compensation Type: {meta['compensation_type']}
Eligibility Criteria: {meta['eligibility']}
Calculation Method: {meta['calculation_method']}
"""


def run_compensation_llm(user_message, matched_rule_block):
    prompt = f"""
You are a banking compensation eligibility engine for Indian banks.

You will receive:
(A) A user complaint message.
(B) The matched compensation policy rule.

Your tasks:
1. Identify which ONE of the following high-priority scenario types best applies:
   - "upi"
   - "atm"
   - "neft"
   - "rtgs"
   - "cheque"
   - "nach_credit"
   - "nach_mandate"
   - "unauth_zero"
   - "unauth_limited"
   - "unauth_negligence"

2. For that scenario ONLY, extract the exact parameters needed for calculation.
   You MUST normalise all dates to ISO format "YYYY-MM-DD".
   If a field is not present or cannot be inferred, return "none" for that field.

3. DO NOT calculate the compensation amount yourself.
   The backend will perform the rupee calculation using these parameters.

Return ONLY a valid JSON object exactly in this format (fields may still be "none"):

{{
 "scenario_type": "upi | atm | neft | rtgs | cheque | nach_credit | nach_mandate | unauth_zero | unauth_limited | unauth_negligence",

 "transaction_amount": "... or none",

 "transaction_date_iso": "... or none",
 "resolved_date_iso": "... or none",

 "due_date_iso": "... or none",
 "credit_date_iso": "... or none",

 "revocation_effective_date_iso": "... or none",
 "resolution_date_iso": "... or none",

 "debit_date_iso": "... or none",
 "reversal_date_iso": "... or none",

 "tat_days": "... or none",

 "repo_rate": "... or none",
 "interest_rate": "... or none",

 "fraud_amount": "... or none",
 "fraud_amount_before_report": "... or none",
 "fraud_amount_after_report": "... or none",
 "account_segment": "... or none",

 "notes": "Short natural language summary of how you mapped the user story and rule to this scenario and parameters."
}}

Do not return anything outside JSON.
Do not use markdown.

--------------------

User Message:
{user_message}

Matched Compensation Rule:
{matched_rule_block}
"""
    res = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role":"user","content":prompt}],
        temperature=0
    )
    return res.choices[0].message.content


def run_compensation_explainer_llm(user_message, llm_data, calc_result, bank_name):
    """
    Turn a successful deterministic calculation into a user-friendly explanation.
    """
    scenario_type = llm_data.get("scenario_type", "unknown")
    amount = calc_result.get("amount")
    tx_amount = calc_result.get("primary_amount")
    tx_date = calc_result.get("primary_date")
    customer_liab = calc_result.get("customer_liability")
    bank_comp = calc_result.get("bank_compensation")
    explanation = calc_result.get("explanation", "")

    prompt = f"""
You are a senior Indian banking customer support assistant.

A user described this compensation complaint:
---
{user_message}
---

The backend compensation engine has ALREADY computed the result using RBI-style rules.
Do NOT recalculate any numbers. Just explain the result clearly.

Here is the structured information you MUST rely on:

- scenario_type: {scenario_type}
- transaction_amount: {tx_amount}
- transaction_date: {tx_date}
- computed_compensation_amount: {amount}
- customer_liability (if present): {customer_liab}
- bank_compensation_share (if present): {bank_comp}
- bank_name (if present): {bank_name}
- internal_engine_explanation: {explanation}

Your task:
1. Explain in simple language why the user is (or is not) eligible.
2. Clearly state the exact rupee compensation the bank should pay, and who bears what amount.
3. Briefly describe how the delay / interest / liability rule was applied (no formulas, just intuition).
4. Mention any relevant note about the bank's own policy if bank_name is present.
5. Keep it short, friendly, and in plain text (no markdown tables, no bullet lists).

Return ONLY the explanation text, no JSON, no extra labels.
"""
    res = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return res.choices[0].message.content


def run_compensation_missing_info_llm(user_message, llm_data, calc_result):
    """
    Ask the user for missing mandatory parameters in a friendly way.
    """
    scenario_type = llm_data.get("scenario_type", "unknown")
    explanation = calc_result.get("explanation", "")

    prompt = f"""
You are a banking compensation assistant.

A user described this complaint:
---
{user_message}
---

The backend compensation engine could NOT calculate any compensation because some
mandatory parameters were missing or unclear.

Scenario type guess: {scenario_type}
Internal engine explanation: {explanation}

Your task:
1. Identify which key pieces of information are missing (for example: exact transaction amount,
   transaction date, date of refund/credit, report date, etc.).
2. Ask the user DIRECT, specific follow-up questions to obtain ONLY the missing mandatory details.
3. Keep the tone polite and concise.
4. Do NOT mention internal fields like 'scenario_type' or 'calc_result' in your reply.

Return ONLY the text you would say to the user, no JSON.
"""
    res = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return res.choices[0].message.content


COMP_COLLECTION = os.getenv("COMP_COLLECTION", "bank_compensation_rules")

def extract_bank_name(user_message):
    prompt = f"""
Extract bank name from this message.
If no bank mentioned return "None".
Return only bank name text, nothing else.

Message:
{user_message}
"""
    res = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role":"user","content":prompt}],
        temperature=0
    )
    name = res.choices[0].message.content.strip()
    if name.lower() == "none":
        return None
    return name



@app.post("/mantra_compensation", response_model=CompensationResponse)
async def mantra_compensation(request: CompensationQuery):

    # ---- Step 1 Embed ----
    emb = get_embedding(request.user_message)

    # ---- Step 2 Vector search ----
    results = zilliz_search("bank_compensation_rules", emb, top_k=5)

    if not results:
        return {
          "transaction_amount":"none",
          "transaction_date":"none",
          "compensation_eligible": False,
          "compensation_amount":"none",
          "other_info":"No matching compensation policy found",
          "bank_name": None,
          "links": None
        }

    # ---- Step 3 Top rule ----
    top_rule = results[0]
    rule_block = format_comp_rule_for_prompt(top_rule)

    # ---- Step 4 LLM structured extraction (no calculation) ----
    llm_json = run_compensation_llm(request.user_message, rule_block)
    try:
        llm_data = json.loads(llm_json)
    except json.JSONDecodeError:
        llm_data = {
          "scenario_type": "none",
          "notes": "LLM JSON parsing failed"
        }

    # ---- Step 5 Deterministic compensation calculation for 10 scenarios ----
    repo_rate_default = float(os.getenv("RBI_REPO_RATE", "0.065"))
    sb_rate_default = float(os.getenv("SB_INTEREST_RATE", "0.03"))

    calc_result = dispatch_compensation(
        llm_data,
        default_repo_rate=repo_rate_default,
        default_sb_rate=sb_rate_default,
    )

    eligible = bool(calc_result.get("eligible"))
    amount_val = calc_result.get("amount")

    if amount_val is not None:
        # normalise to string rupee value (no decimals if integer)
        if isinstance(amount_val, float) and amount_val.is_integer():
            compensation_amount = str(int(amount_val))
        else:
            compensation_amount = str(amount_val)
    else:
        compensation_amount = "none"

    primary_amount = calc_result.get("primary_amount")
    if primary_amount is not None:
        if isinstance(primary_amount, float) and primary_amount.is_integer():
            transaction_amount = str(int(primary_amount))
        else:
            transaction_amount = str(primary_amount)
    else:
        transaction_amount = "none"

    transaction_date = calc_result.get("primary_date") or "none"

    # ---- Step 6 Extract bank name ----
    bank_name = extract_bank_name(request.user_message)

    # ---- Step 7 Lookup policy links if bank found ----
    links = None
    if bank_name:
        links = lookup_bank_links(bank_name)

    # ---- Step 8 Build user-facing explanation in other_info ----
    if eligible and amount_val is not None:
        # Case 1: calculation succeeded -> explain result
        other_info = run_compensation_explainer_llm(
            request.user_message,
            llm_data,
            calc_result,
            bank_name,
        )
    else:
        # Case 2: calculation not possible -> ask for missing info
        other_info = run_compensation_missing_info_llm(
            request.user_message,
            llm_data,
            calc_result,
        )

    # ---- Step 9 Final response ----
    return {
      "transaction_amount": transaction_amount,
      "transaction_date": transaction_date,
      "compensation_eligible": eligible,
      "compensation_amount": compensation_amount,
      "other_info": other_info,
      "bank_name": bank_name,
      "links": links
    }

