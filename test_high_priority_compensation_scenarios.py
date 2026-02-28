import requests
import json

API_URL = "http://127.0.0.1:8000/mantra_compensation"
OUTPUT_FILE = "compensation_test_results_high_priority.json"

today = "8 February 2026"

scenarios = [
    {
        "label": "UPI failure - P2P credit not received",
        "story": f"""Today is {today}. I am an Axis Bank customer.
On 12 January 2026 I sent ₹2,500 using UPI to my friend's UPI ID.
The amount was debited from my account but my friend never received the money.
The bank did not auto-reverse the amount by the usual UPI T+1 deadline (13 January 2026).
The refund finally reached my account only on 20 January 2026, which is 7 days after the T+1 deadline.
I want compensation of ₹100 per day of delay beyond T+1 as per the failed UPI transaction rules.""",
    },
    {
        "label": "ATM cash withdrawal - cash not dispensed",
        "story": f"""Today is {today}. I am an SBI customer.
On 3 January 2026 I tried withdrawing ₹5,000 from an ATM in Delhi.
The machine showed processing but cash never came out while my account was debited.
The bank did not reverse the debit within the T+5 days ATM reversal period (by 8 January 2026).
The amount was finally reversed only on 18 January 2026, well after T+5.
I want compensation of ₹100 per day of delay beyond T+5 as per the ATM failed transaction rules.""",
    },
    {
        "label": "NEFT credit delay",
        "story": f"""Today is {today}. I initiated a NEFT transfer of ₹50,000 from my ICICI Bank account
on 15 January 2026 to another bank. The beneficiary bank did not credit the amount within the
normal NEFT credit timeline and the funds were actually credited only 3 days later.
I want compensation for the delay in credit as per NEFT Repo+2% rules.""",
    },
    {
        "label": "RTGS credit delay",
        "story": f"""Today is {today}. I sent ₹2,00,000 using RTGS from my HDFC Bank account
on 10 January 2026. The beneficiary account should have been credited almost immediately,
but the credit was actually given only on 11 January 2026, one full day later beyond the RTGS cut-off.
The current RBI repo rate is 6.5%, so the compensation rate should be 8.5% per annum (Repo + 2%)
on the RTGS amount for at least 1 day of delay.
I am seeking compensation for this RTGS delay as per the Repo+2% guidelines.""",
    },
    {
        "label": "Cheque collection delay",
        "story": f"""Today is {today}. I deposited an outstation cheque of ₹20,000 into my savings account
on 1 January 2026. As per the bank's cheque collection policy, the cheque should have been cleared
within 10 days (by 11 January 2026), but it was actually credited only on 16 January 2026,
which is a delay of 5 days beyond the policy TAT.
My savings bank interest rate is 3% per annum, and compensation should be calculated at 3% for 5 days
on ₹20,000 as per the cheque collection delay grid.
I want compensation for the delay in cheque collection as per the bank's policy grid.""",
    },
    {
        "label": "NACH credit delay",
        "story": f"""Today is {today}. A NACH credit for a government subsidy of ₹1,200 was due to be credited
to my account on 5 January 2026. However, the bank credited the amount only on 9 January 2026,
which is beyond the T+1 day NACH/APBS credit timeline.
I am asking for compensation for this NACH credit delay.""",
    },
    {
        "label": "NACH mandate - debit after revocation",
        "story": f"""Today is {today}. I revoked a NACH mandate for a loan EMI from my HDFC Bank account
on 1 January 2026 and the bank confirmed the revocation. Despite this, the bank still debited
₹5,000 on 3 January 2026 under the old mandate and reversed it only on 10 January 2026.
I want compensation for the delay in resolving this wrongful NACH debit after revocation.""",
    },
    {
        "label": "Unauthorised electronic txn - zero liability",
        "story": f"""Today is {today}. A fraudulent online transaction of ₹30,000 was done on my debit card
on 1 January 2026 without my knowledge. I received the SMS alert the same day and reported the fraud
to the bank on 2 January 2026, within 3 working days. The bank reversed the principal amount only
on 12 January 2026. I want compensation for interest loss under the zero liability rule.""",
    },
    {
        "label": "Unauthorised electronic txn - limited liability (4-7 days)",
        "story": f"""Today is {today}. I hold a normal savings bank account. A third-party fraud of ₹20,000
happened through internet banking on 1 January 2026.
I did NOT share any OTP, PIN, password, or credentials at any time and there was no negligence on my part.
The fraud was due to a third-party breach. I reported the fraud to the bank on 6 January 2026,
which is between 4 and 7 working days from the alert.
Under the RBI 'unauthorised electronic transaction - limited liability (4-7 days)' framework,
for a normal savings bank account my account segment should be treated as savings/PPIs with the
relevant liability cap, not as customer negligence.
I want compensation as per the limited liability rules for savings bank accounts.""",
    },
    {
        "label": "Unauthorised electronic txn - customer negligence",
        "story": f"""Today is {today}. I mistakenly shared an OTP with a caller and due to this,
fraudulent debits of ₹40,000 happened from my account before I reported the incident to the bank
on 5 January 2026. After I reported, an additional fraudulent debit of ₹5,000 was attempted and
went through before the bank could block the channel. I want the bank to apply the customer
negligence rules where I bear losses before reporting but the bank bears losses after reporting.""",
    },
]


def main():
    results = []

    for i, item in enumerate(scenarios, start=1):
        label = item["label"]
        story = item["story"]

        print(f"Running High-Priority Scenario {i}: {label}...")

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

    print("\n✅ All high-priority compensation tests completed.")
    print("Results saved in:", OUTPUT_FILE)


if __name__ == "__main__":
    main()

