import requests
import json

API_URL = "http://127.0.0.1:8000/mantra_compensation"
OUTPUT_FILE = "compensation_test_results_high_priority_negative.json"

today = "8 February 2026"

# Each scenario below intentionally omits at least one mandatory parameter
# (amount and/or specific dates) so that the deterministic calculators
# cannot compute a compensation amount. This triggers the "missing info"
# LLM flow in the API.

scenarios = [
    {
        "label": "NEG UPI - missing amount",
        "story": f"""Today is {today}. I am an Axis Bank customer.
Last week I sent some money using UPI to a friend's UPI ID.
The amount was debited from my account but my friend never received the money.
I do not remember the exact transaction amount or the exact date, but it was in early January 2026.
No refund has been received till now and I want to know if I am eligible for compensation.""",
    },
    {
        "label": "NEG ATM - missing refund date",
        "story": f"""Today is {today}. I am an SBI customer.
On 3 January 2026 I tried withdrawing ₹5,000 from an ATM in Delhi.
The machine showed processing but cash never came out while my account was debited.
I raised a complaint but I am not sure on which exact date the refund came back to my account.
Please check whether I am eligible for any ATM failed transaction compensation.""",
    },
    {
        "label": "NEG NEFT - missing delay days",
        "story": f"""Today is {today}. I initiated a NEFT transfer from my ICICI Bank account
around mid-January 2026. The beneficiary told me that the credit was delayed compared to
the normal NEFT credit timelines, but I do not know the exact debit date or the exact date
on which the funds were credited. I also do not recall the exact amount transferred.
I want to know if I am eligible for any NEFT delay compensation.""",
    },
    {
        "label": "NEG RTGS - missing amount",
        "story": f"""Today is {today}. I sent a large RTGS payment from my HDFC Bank account
in the first week of January 2026. The beneficiary informed me that the credit was given
with some delay beyond the RTGS cut-off, but I do not remember the exact transaction amount
or the exact dates of debit and credit. I want to check if any RTGS delay compensation applies.""",
    },
    {
        "label": "NEG Cheque - missing interest rate",
        "story": f"""Today is {today}. I deposited an outstation cheque into my savings account
at the beginning of January 2026. The cheque was credited several days later than the usual
collection timeline, but I do not know my savings bank interest rate or the exact number of days
of delay. I would like to know if I am eligible for any cheque collection delay compensation.""",
    },
    {
        "label": "NEG NACH credit - missing due date",
        "story": f"""Today is {today}. A NACH credit for a government subsidy was expected
into my account sometime in early January 2026. The amount was credited after a few days'
delay compared to when I was told it would come, but I do not know the exact due date or
the exact credit date. I want to understand if any NACH/APBS credit delay compensation is possible.""",
    },
    {
        "label": "NEG NACH mandate - missing revocation date",
        "story": f"""Today is {today}. I had asked my bank to revoke a NACH mandate for a loan EMI,
but I do not remember the exact date on which the revocation became effective.
After that, the bank still debited one more EMI from my account and reversed it later.
I am not sure about the exact debit and reversal dates. I want to know if I can claim any
compensation for this NACH debit after revocation.""",
    },
    {
        "label": "NEG Unauth zero - missing fraud date",
        "story": f"""Today is {today}. A fraudulent online transaction happened on my debit card
recently and the bank later reversed the amount. I reported it quickly after getting the SMS alert,
but I do not recall the exact date of the fraud, the date I reported it, or the date of reversal.
I want to know whether the zero-liability unauthorised electronic transaction rule can apply here.""",
    },
    {
        "label": "NEG Unauth limited - missing account segment",
        "story": f"""Today is {today}. A third-party fraud happened through internet banking and
about ₹20,000 was debited from my account. I reported the fraud after a few days but within a week
of the alert SMS. I am not sure what exact type of account I hold (basic, savings, current, etc.).
I want to check if the limited-liability unauthorised electronic transaction rules give me any compensation.""",
    },
    {
        "label": "NEG Unauth negligence - missing split before/after report",
        "story": f"""Today is {today}. Due to my own mistake of sharing an OTP with a caller,
multiple fraudulent transactions were done on my account over a few days.
I reported the issue to the bank at some point, but I do not remember how much was debited
before I reported and how much was debited after reporting.
I want to understand what part of the loss I may have to bear and what part the bank should bear
under the customer negligence rules.""",
    },
]


def main():
    results = []

    for i, item in enumerate(scenarios, start=1):
        label = item["label"]
        story = item["story"]

        print(f"Running NEG High-Priority Scenario {i}: {label}...")

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

    print("\n✅ All NEGATIVE high-priority compensation tests completed.")
    print("Results saved in:", OUTPUT_FILE)


if __name__ == "__main__":
    main()

