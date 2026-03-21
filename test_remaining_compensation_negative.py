import requests
import json

API_URL = "http://127.0.0.1:8000/mantra_compensation"
OUTPUT_FILE = "compensation_test_results_remaining_negative.json"

today = "1 March 2026"

# Each scenario below intentionally omits at least one mandatory parameter
# (amount and/or specific dates) so that the deterministic calculators
# cannot compute a compensation amount. This triggers the "missing info"
# LLM flow in the API.

scenarios = [
    {
        "label": "NEG CIR / Credit-Report - missing resolution date",
        "story": f"""Today is {today}. I filed a CIR / credit-report dispute with my bank on 1 January 2026.
The corrected data was sent to me later.
Please calculate my compensation."""
    },
    {
        "label": "NEG Card to Card Transfer - missing amount and resolution date",
        "story": f"""Today is {today}. I tried transferring from one card to another card on 10 January 2026.
The beneficiary card did not get credited and it was resolved later.
Can you tell me if I am eligible for compensation?"""
    },
    {
        "label": "NEG Cheque Lost in Transit - missing credit date and amount",
        "story": f"""Today is {today}. I deposited an outstation cheque on 1 January 2026.
The cheque was lost in transit and the actual credit came much later.
What compensation am I eligible for?"""
    },
    {
        "label": "NEG Cheque Paid After Stop-Payment - missing original debit date",
        "story": f"""Today is {today}. I gave stop-payment instruction for a cheque of ₹25,000 before the bank presented it.
However, the cheque was still paid and the credit/payment posted to my account.
What compensation should I get?"""
    },
    {
        "label": "NEG Credit Card Delayed Closure - missing closure date",
        "story": f"""Today is {today}. I requested closure of my credit card on 1 January 2026.
There were no outstanding dues. The bank failed to close the card within the required time and it got closed later.
I want to know my compensation for this delay."""
    },
    {
        "label": "NEG Credit Card Issued Without Consent - missing reversed amount",
        "story": f"""Today is {today}. A credit card was issued and activated without my written digital consent.
I disputed the charges, and I did not use the card at all. The charges were reversed.
Can you calculate my compensation?"""
    },
    {
        "label": "NEG Delay in Return of Loan Security Docs - missing return date",
        "story": f"""Today is {today}. I fully repaid my loan and repayment was completed on 1 January 2026.
The bank returned the title/security documents after a significant delay.
Compute the compensation for this delay."""
    },
    {
        "label": "NEG ECS/Direct Debit - missing execution date",
        "story": f"""Today is {today}. My valid ECS/Direct Debit mandate was scheduled to execute on 1 January 2026.
Due to bank failure, it actually got executed late. I also incurred some customer penalties at other banks.
Please tell me if I am eligible for compensation."""
    },
    {
        "label": "NEG Erroneous Debit - missing exact debit amount",
        "story": f"""Today is {today}. I was wrongly debited/duplicate debited by the bank due to a staff error.
The bank reversed it later.
Compute compensation for this."""
    },
    {
        "label": "NEG Failed IMPS - missing resolution date",
        "story": f"""Today is {today}. My IMPS transaction of ₹8,000 failed (beneficiary not credited) and the amount was debited on 10 January 2026.
The funds were resolved later.
Assume T+1 applies and compute compensation."""
    },
    {
        "label": "NEG FD Failed Maturity Instruction - missing lost interest amount",
        "story": f"""Today is {today}. I provided maturity instruction for a Fixed Deposit before the cut-off.
The bank failed to execute it properly, and I suffered lost interest compared to the intended outcome.
Compute compensation."""
    },
    {
        "label": "NEG Investment Slip Processing Delay - missing processing date",
        "story": f"""Today is {today}. I submitted a mutual fund investment slip on 1 January 2026 for ₹1,00,000.
The processing completed with a delay.
Compute compensation for the delay."""
    },
    {
        "label": "NEG Duplicate DD Delay - missing issue date",
        "story": f"""Today is {today}. I requested a duplicate demand draft for ₹50,000 on 1 January 2026.
The duplicate demand draft was issued late.
Compute compensation."""
    },
    {
        "label": "NEG Locker Loss Due to Bank Negligence - missing annual rent",
        "story": f"""Today is {today}. My locker contents were lost due to bank negligence at the bank premises.
Compute compensation."""
    },
    {
        "label": "NEG Violation by Bank's Agent - missing financial loss",
        "story": f"""Today is {today}. I am complaining about improper conduct / violation by the bank's agent (DSA) within bank scope.
I had some direct financial loss.
Compute compensation."""
    },
]


def main():
    results = []

    for i, item in enumerate(scenarios, start=1):
        label = item["label"]
        story = item["story"]

        print(f"Running NEG Remaining Scenario {i}: {label}...")

        payload = {"user_message": story}

        try:
            response = requests.post(API_URL, json=payload, timeout=60)
            response_json = response.json()
        except Exception as e:
            response_json = {"error": str(e)}

        results.append(
            {
                "scenario_id": i,
                "label": label,
                "user_story": story,
                "api_response": response_json,
            }
        )

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("\n✅ All NEGATIVE remaining compensation tests completed.")
    print("Results saved in:", OUTPUT_FILE)


if __name__ == "__main__":
    main()
