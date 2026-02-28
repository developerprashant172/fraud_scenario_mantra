# app/compensation_rules.py

COMP_RULES = {

    # 1–4 Payment / transfer delays
    1: {"type": "delay", "allowed_days": 1, "per_day": 100},
    2: {"type": "delay", "allowed_days": 5, "per_day": 100},
    3: {"type": "delay", "allowed_days": 1, "per_day": 100},
    4: {"type": "delay", "allowed_days": 5, "per_day": 100},

    # 5–6 Interest compensation
    5: {"type": "interest", "rate": 0.08},
    6: {"type": "interest", "rate": 0.08},

    # 7–8 Wallet/card delay
    7: {"type": "delay", "allowed_days": 1, "per_day": 100},
    8: {"type": "delay", "allowed_days": 1, "per_day": 100},

    # 9 Low interest delay
    9: {"type": "interest", "rate": 0.04},

    # 10–13 Refund types
    10: {"type": "refund"},
    11: {"type": "refund"},
    12: {"type": "refund"},
    13: {"type": "refund"},

    # 14 Limited liability
    14: {"type": "limited_refund", "limit": 10000},

    # 15 Customer negligence
    15: {"type": "no_comp"},

    # 16 Weekly capped delay
    16: {"type": "weekly_delay", "per_week": 100, "cap": 5000},

    # 17 Bank error reversal
    17: {"type": "refund"},

    # 18 Locker delay
    18: {"type": "delay", "allowed_days": 7, "per_day": 500},

    # 19 Account closure delay
    19: {"type": "delay", "allowed_days": 30, "per_day": 100},

    # 20–21 ATM delays
    20: {"type": "delay", "allowed_days": 5, "per_day": 100},
    21: {"type": "delay", "allowed_days": 1, "per_day": 100},

    # 22 SB interest limits
    22: {
        "type": "interest_with_limits",
        "rate": 0.03,
        "min": 100,
        "max": 1000,
    },

    # 23–24 FD interest
    23: {"type": "interest", "rate": 0.06},
    24: {"type": "interest", "rate": 0.06},

    # 25 Investment delay
    25: {"type": "interest", "rate": 0.05},

    # 26 Locker loss
    26: {"type": "locker_loss", "multiplier": 100},

    # 27 Actual loss reimbursement
    27: {"type": "refund"},
}
