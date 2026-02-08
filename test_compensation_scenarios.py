import requests
import json

API_URL = "http://127.0.0.1:8000/mantra_compensation"
OUTPUT_FILE = "compensation_test_results.json"

today = "8 February 2026"

stories = [
    f"""Today is {today}. I am an SBI customer. On 3 January 2026 around 8:30 PM,
    I tried withdrawing ₹5,000 from an ATM in Delhi. The machine showed processing
    but cash never came out. However, my account was debited instantly.
    I immediately contacted customer care and filed a complaint but refund has still
    not been credited.""",

    f"""Today is {today}. I withdrew ₹10,000 from an HDFC ATM on 10 January 2026,
    but only ₹6,000 was dispensed while the full amount got debited.
    I raised complaint same day but refund is still pending.""",

    f"""Today is {today}. I sent ₹2,500 using UPI from my Axis Bank account on
    12 January 2026 to a merchant, but the merchant never received it while money
    got debited. Complaint raised but refund not received.""",

    f"""Today is {today}. On 5 January 2026, my UPI payment of ₹4,000 failed due to
    network issue but amount was debited and still not refunded.""",

    f"""Today is {today}. I transferred ₹7,500 using IMPS on 7 January 2026.
    Transaction failed but amount is still not reversed after complaint.""",

    f"""Today is {today}. I sent ₹12,000 using NEFT from ICICI Bank on 15 January
    2026 but beneficiary never received money and refund is still pending.""",

    f"""Today is {today}. Axis Bank debited ₹1,200 twice for same electricity bill
    payment on 8 January 2026 and duplicate debit has not been reversed.""",

    f"""Today is {today}. Debit card payment of ₹3,500 failed at an online store
    on 2 January 2026 but amount got deducted and not refunded.""",

    f"""Today is {today}. POS machine declined payment of ₹2,200 at supermarket
    on 4 January 2026 but amount got deducted from my account.""",

    f"""Today is {today}. Net banking payment of ₹9,000 failed on 4 January 2026
    due to server error but bank debited my account.""",

    f"""Today is {today}. Merchant processed refund of ₹1,500 on 6 January 2026
    but amount is not credited back to my account.""",

    f"""Today is {today}. ATM retained my debit card on 11 January 2026 during
    withdrawal and bank has not yet returned or replaced it.""",

    f"""Today is {today}. Fraud debit of ₹6,000 happened on 1 January 2026,
    but I noticed after several days and reported late to bank.""",

    f"""Today is {today}. Fraudulent debit of ₹8,000 occurred on 14 January 2026
    and I immediately informed bank within minutes.""",

    f"""Today is {today}. Wallet payment of ₹600 failed on 9 January 2026
    but money was debited and refund not received.""",

    f"""Today is {today}. Merchant refunded ₹2,700 on 3 January 2026 but money
    still not credited into my account.""",

    f"""Today is {today}. Bank charged ATM withdrawal fee wrongly on 7 January 2026
    even though transaction failed.""",

    f"""Today is {today}. Cash deposit machine accepted ₹10,000 on 6 January 2026
    but amount not credited to my account.""",

    f"""Today is {today}. EMI auto debit of ₹5,000 failed on 8 January 2026 but
    penalty got applied by lender due to delay.""",

    f"""Today is {today}. Chargeback refund of ₹3,300 promised on 5 January 2026
    has not yet been credited.""",

    f"""Today is {today}. Credit card refund of ₹4,500 processed on 2 January 2026
    is still not reflected in account.""",

    f"""Today is {today}. ATM withdrawal of ₹4,000 was debited twice on
    10 January 2026.""",

    f"""Today is {today}. ATM withdrawal of ₹6,000 failed on 5 January 2026 but
    amount got debited.""",

    f"""Today is {today}. Restaurant POS machine declined payment of ₹1,800 on
    9 January 2026 but account was charged.""",

    f"""Today is {today}. Due to technical error, ₹900 got deducted wrongly from
    my bank account on 13 January 2026.""",

    f"""Today is {today}. Airline refunded ₹7,000 for ticket cancellation on
    4 January 2026 but amount not credited yet.""",

    f"""Today is {today}. QR payment of ₹850 failed on 12 January 2026 but amount
    got debited from account.""",

    f"""Today is {today}. Mobile banking payment of ₹2,100 failed on
    15 January 2026 but amount deducted."""
]

results = []

for i, story in enumerate(stories, start=1):
    print(f"Running Scenario {i}...")

    payload = {"user_message": story}

    try:
        response = requests.post(API_URL, json=payload, timeout=60)
        response_json = response.json()
    except Exception as e:
        response_json = {"error": str(e)}

    results.append({
        "scenario_id": i,
        "user_story": story,
        "api_response": response_json
    })

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print("\n✅ All compensation tests completed.")
print("Results saved in:", OUTPUT_FILE)
