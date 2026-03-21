import requests
import json

API_URL = "http://127.0.0.1:8000/mantra_compensation"
OUTPUT_FILE = "compensation_test_results_remaining.json"

today = "1 March 2026"

scenarios = [
    {
        "label": "CIR / Credit-Report Correction Delay",
        "story": f"""Today is {today}. I filed a CIR / credit-report dispute with my bank on 1 January 2026.
The corrected data was sent/resolved on 20 February 2026.
Please calculate compensation as Rs 100 per day beyond the 30-day correction window."""
    },
    {
        "label": "Card to Card Transfer Failure (T+1)",
        "story": f"""Today is {today}. I tried transferring from one card to another card on 10 January 2026 for ₹12,000.
The beneficiary card did not get credited and it was resolved only on 12 January 2026.
Assume T+1 applies, so compute Rs 100 per day beyond T+1."""
    },
    {
        "label": "Cheque Lost in Transit",
        "story": f"""Today is {today}. I deposited an outstation cheque of ₹20,000 on 1 January 2026.
The cheque was lost in transit and the actual credit/information came only on 25 January 2026.
Cheque collection TAT is 10 days and cheque collection interest rate is 3% per annum.
SB interest rate is 3% per annum.
My documented costs (stop payment, duplicate, etc.) are ₹400, but the rule caps documented costs at ₹250.
Compute compensation using: interest beyond TAT + interest for extra 15 days at SB rate + capped costs."""
    },
    {
        "label": "Cheque Paid After Stop-Payment",
        "story": f"""Today is {today}. I gave stop-payment instruction for a cheque of ₹25,000 before the bank presented it.
However, the cheque was still paid and the credit/payment posted to my account on 10 January 2026.
The original debit date was 1 January 2026.
SB interest rate is 3% per annum.
Downstream charges/interest impact (min-balance penalty, extra interest impact, etc.) is ₹500.
Compute compensation as: cheque amount reversal + value-dated interest impact + downstream charges impact."""
    },
    {
        "label": "Credit Card - Delayed Closure",
        "story": f"""Today is {today}. I requested closure of my credit card on 1 January 2026.
There were no outstanding dues.
The bank failed to close the card within the required T+7 working days.
It got closed later, and the delay beyond T+7 working days is 5 working days.
Compute compensation as Rs 500 per day beyond T+7."""
    },
    {
        "label": "Credit Card - Issued Without Consent",
        "story": f"""Today is {today}. A credit card was issued and activated without my written digital consent.
I disputed the charges, and I did not use the card at all.
Total charges reversed due to the dispute are ₹1,500.
Compute compensation as 2 × charges reversed."""
    },
    {
        "label": "Delay in Return of Loan Security Docs",
        "story": f"""Today is {today}. I fully repaid my loan and repayment was completed on 1 January 2026.
For my product, the allowed return period is 15 working days.
The bank returned the title/security documents after an additional 20 working days beyond the allowed period.
This is NOT a premium product, so it is Rs 100 per week (not per day).
Cap amount for this compensation is ₹5,000.
Compute the compensation accordingly."""
    },
    {
        "label": "ECS/Direct Debit - Failed/Delayed Execution",
        "story": f"""Today is {today}. My valid ECS/Direct Debit mandate was scheduled to execute on 1 January 2026.
Due to bank failure, it actually got executed on 6 January 2026.
The amount involved was ₹10,000.
SB interest rate is 3% per annum.
Customer penalties/charges at other banks due to the failure are ₹500.
Compute compensation as SB-rate interest for delay period (clamped between ₹100 and ₹1,000) + customer penalties."""
    },
    {
        "label": "Erroneous Debit (Bank Error)",
        "story": f"""Today is {today}. I was wrongly debited/duplicate debited by the bank for ₹30,000.
The bank reversed it later, but I suffered an interest loss of ₹1,000 and downstream charges reversal of ₹500.
This involved a bank staff error / staff-fraud case, so apply the +1% staff-fraud uplift.
Compute compensation as interest loss + downstream reversal + 1% uplift in staff-fraud cases."""
    },
    {
        "label": "Failed IMPS (T+1)",
        "story": f"""Today is {today}. My IMPS transaction of ₹8,000 failed (beneficiary not credited) and the amount was debited on 10 January 2026.
The funds were resolved (auto-reversal / credit) only on 12 January 2026.
Assume T+1 applies and compute Rs 100 per day beyond T+1."""
    },
    {
        "label": "FD - Failed Action on Maturity Instruction",
        "story": f"""Today is {today}. I provided maturity instruction for a Fixed Deposit before the cut-off.
The bank failed to execute it properly, and I suffered lost interest of ₹2,500 compared to the intended outcome.
Compute compensation as the lost interest amount."""
    },
    {
        "label": "Investment/Redemption Slip - Processing Delay (Mutual Fund)",
        "story": f"""Today is {today}. I submitted a mutual fund investment/redemption slip on 1 January 2026 for ₹1,00,000.
The processing completed on 11 January 2026 (delay).
SB interest rate for delay compensation is 3% per annum.
This is NOT an SGB rejection case.
Compute compensation as SB-rate interest for delayed period."""
    },
    {
        "label": "Duplicate Demand Draft - Delay",
        "story": f"""Today is {today}. I requested a duplicate demand draft for ₹50,000 on 1 January 2026.
The duplicate demand draft was issued on 11 January 2026.
Corresponding FD rate for that maturity period is 6% per annum.
Compute compensation using the FD-rate interest for the delay."""
    },
    {
        "label": "Locker - Loss Due to Bank Negligence",
        "story": f"""Today is {today}. My locker contents were lost due to bank negligence at the bank premises.
Annual locker rent is ₹200.
The policy cap for locker loss compensation is ₹25,000.
Compute compensation as 100 × annual locker rent, capped by the cap."""
    },
    {
        "label": "Violation by Bank's Agent",
        "story": f"""Today is {today}. I am complaining about improper conduct / violation by the bank's agent (DSA/courier/representative) within bank scope.
My actual direct financial loss is ₹10,000.
Compute compensation as the actual direct financial loss only."""
    },
]


def main():
    results = []

    for i, item in enumerate(scenarios, start=1):
        label = item["label"]
        story = item["story"]

        print(f"Running Remaining Scenario {i}: {label}...")

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

    print("\n✅ All remaining compensation tests completed.")
    print("Results saved in:", OUTPUT_FILE)


if __name__ == "__main__":
    main()

