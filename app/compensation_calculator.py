from datetime import datetime
from app.compensation_rules import COMP_RULES


def parse_date(date_str):
    return datetime.strptime(date_str, "%Y-%m-%d")


def days_between(d1, d2):
    return max(0, (d2 - d1).days)


def calculate_compensation(scenario_id, txn_date, today_date, amount):

    rule = COMP_RULES.get(scenario_id)
    if not rule:
        return 0

    txn = parse_date(txn_date)
    today = parse_date(today_date)
    delay = days_between(txn, today)

    rtype = rule["type"]

    # Delay compensation
    if rtype == "delay":
        extra = max(0, delay - rule["allowed_days"])
        return extra * rule["per_day"]

    # Weekly capped delay
    if rtype == "weekly_delay":
        weeks = delay // 7
        comp = weeks * rule["per_week"]
        return min(comp, rule["cap"])

    # Interest compensation
    if rtype == "interest":
        return round(amount * rule["rate"] * delay / 365)

    # Interest with limits
    if rtype == "interest_with_limits":
        comp = amount * rule["rate"] * delay / 365
        comp = max(rule["min"], comp)
        return min(comp, rule["max"])

    # Refund cases
    if rtype == "refund":
        return amount

    # Limited refund
    if rtype == "limited_refund":
        return min(amount, rule["limit"])

    # Locker loss
    if rtype == "locker_loss":
        return amount * rule["multiplier"]

    # No compensation
    if rtype == "no_comp":
        return 0

    return 0
