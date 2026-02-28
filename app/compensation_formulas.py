from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, Dict, Any


def _parse_iso_date(value: Optional[str]) -> Optional[date]:
    if not value or value == "none":
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception:
        return None


def _parse_float(value: Optional[str]) -> Optional[float]:
    if value is None or value == "" or str(value).lower() == "none":
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return None


def _parse_int(value: Optional[str]) -> Optional[int]:
    f = _parse_float(value)
    return int(f) if f is not None else None


@dataclass
class CompensationContext:
    """Normalised, LLM-extracted fields used by calculators."""

    scenario_type: str
    raw: Dict[str, Any]

    @classmethod
    def from_llm(cls, data: Dict[str, Any]) -> "CompensationContext":
        scen = (data.get("scenario_type") or "").strip().lower()
        return cls(scenario_type=scen, raw=data)

    # Common helpers
    def amount(self, key: str = "transaction_amount") -> Optional[float]:
        return _parse_float(self.raw.get(key))

    def iso_date(self, key: str) -> Optional[date]:
        return _parse_iso_date(self.raw.get(key))

    def int_field(self, key: str) -> Optional[int]:
        return _parse_int(self.raw.get(key))

    def float_field(self, key: str) -> Optional[float]:
        return _parse_float(self.raw.get(key))


# ----------------------------
# Scenario-specific calculators
# ----------------------------

def calc_upi_compensation(ctx: CompensationContext) -> Optional[int]:
    """
    Failed UPI (P2P / P2M) per RBI grid.
    Expects:
    - transaction_amount (not used in formula but useful for validation)
    - transaction_date_iso
    - resolved_date_iso   (or today if still pending)
    - tat_days            (1 for P2P, 5 for P2M)
    """
    txn_date = ctx.iso_date("transaction_date_iso")
    resolved_date = ctx.iso_date("resolved_date_iso")
    tat_days = ctx.int_field("tat_days") or 1

    if not txn_date or not resolved_date:
        return None

    total_delay = (resolved_date - txn_date).days
    delay_beyond_tat = max(0, total_delay - tat_days)
    return delay_beyond_tat * 100


def calc_atm_compensation(ctx: CompensationContext) -> Optional[int]:
    """
    Failed ATM cash withdrawal / POS-eCommerce per RBI grid.
    Expects:
    - transaction_date_iso
    - resolved_date_iso
    - tat_days (defaults to 5)
    """
    txn_date = ctx.iso_date("transaction_date_iso")
    resolved_date = ctx.iso_date("resolved_date_iso")
    tat_days = ctx.int_field("tat_days") or 5

    if not txn_date or not resolved_date:
        return None

    total_delay = (resolved_date - txn_date).days
    delay_beyond_tat = max(0, total_delay - tat_days)
    return delay_beyond_tat * 100


def calc_neft_compensation(
    ctx: CompensationContext,
    default_repo_rate: float,
    spread: float = 0.02,
) -> Optional[float]:
    """
    NEFT delay – Repo + 2% p.a. for days of delay.
    Expects:
    - transaction_amount
    - due_date_iso
    - credit_date_iso
    - repo_rate (optional, overrides default)
    """
    amount = ctx.amount("transaction_amount")
    due_date = ctx.iso_date("due_date_iso")
    credit_date = ctx.iso_date("credit_date_iso")
    repo_rate = ctx.float_field("repo_rate") or default_repo_rate

    if amount is None or not due_date or not credit_date:
        return None

    days_delayed = (credit_date - due_date).days
    if days_delayed <= 0:
        return 0.0

    rate = repo_rate + spread
    return round(amount * rate * days_delayed / 365.0, 2)


def calc_rtgs_compensation(
    ctx: CompensationContext,
    default_repo_rate: float,
    spread: float = 0.02,
) -> Optional[float]:
    """
    RTGS delay – Repo + 2% p.a., minimum 1 day if any delay.
    Expects same fields as NEFT.
    """
    amount = ctx.amount("transaction_amount")
    due_date = ctx.iso_date("due_date_iso")
    credit_date = ctx.iso_date("credit_date_iso")
    repo_rate = ctx.float_field("repo_rate") or default_repo_rate

    if amount is None or not due_date or not credit_date:
        return None

    days_raw = (credit_date - due_date).days
    if days_raw <= 0:
        return 0.0

    days_delayed = max(1, days_raw)
    rate = repo_rate + spread
    return round(amount * rate * days_delayed / 365.0, 2)


def calc_cheque_delay_compensation(ctx: CompensationContext) -> Optional[float]:
    """
    Domestic cheque collection delay.
    Expects:
    - transaction_amount
    - delay_days
    - interest_rate (already SB or TD+2% as per rule)
    """
    amount = ctx.amount("transaction_amount")
    days_delayed = ctx.int_field("delay_days")
    rate = ctx.float_field("interest_rate")

    if amount is None or days_delayed is None or rate is None:
        return None

    if days_delayed <= 0:
        return 0.0

    return round(amount * rate * days_delayed / 365.0, 2)


def calc_nach_credit_compensation(ctx: CompensationContext) -> Optional[int]:
    """
    NACH/APBS credit delay – Rs 100 per day beyond T+1.
    Expects:
    - due_date_iso
    - credit_date_iso
    - tat_days (defaults to 1)
    """
    due_date = ctx.iso_date("due_date_iso")
    credit_date = ctx.iso_date("credit_date_iso")
    tat_days = ctx.int_field("tat_days") or 1

    if not due_date or not credit_date:
        return None

    total_delay = (credit_date - due_date).days
    delay_beyond_tat = max(0, total_delay - tat_days)
    return delay_beyond_tat * 100


def calc_nach_mandate_compensation(ctx: CompensationContext) -> Optional[int]:
    """
    NACH – debit despite mandate revocation.
    Expects:
    - revocation_effective_date_iso
    - resolution_date_iso
    - tat_days (defaults to 1)
    """
    revocation_date = ctx.iso_date("revocation_effective_date_iso")
    resolution_date = ctx.iso_date("resolution_date_iso")
    tat_days = ctx.int_field("tat_days") or 1

    if not revocation_date or not resolution_date:
        return None

    total_delay = (resolution_date - revocation_date).days
    delay_beyond_tat = max(0, total_delay - tat_days)
    return delay_beyond_tat * 100


def calc_unauth_zero_liability_interest(
    ctx: CompensationContext,
    default_interest_rate: float,
) -> Optional[float]:
    """
    Unauthorised electronic transaction – zero liability.
    We assume principal refund is handled by the bank; this returns extra interest.
    Expects:
    - fraud_amount
    - debit_date_iso
    - reversal_date_iso
    - interest_rate (optional, overrides default)
    """
    amount = ctx.amount("fraud_amount")
    debit_date = ctx.iso_date("debit_date_iso")
    reversal_date = ctx.iso_date("reversal_date_iso")
    rate = ctx.float_field("interest_rate") or default_interest_rate

    if amount is None or not debit_date or not reversal_date:
        return None

    days = max(0, (reversal_date - debit_date).days)
    return round(amount * rate * days / 365.0, 2)


ACCOUNT_CAPS = {
    "bsbd": 5000.0,
    "sb_ppi": 10000.0,
    "current_cc": 25000.0,
}


def calc_unauth_limited_liability(ctx: CompensationContext) -> Optional[Dict[str, float]]:
    """
    Unauthorised electronic transaction – limited liability (4–7 days).
    Expects:
    - fraud_amount
    - account_segment in {'bsbd','sb_ppi','current_cc'}
    """
    amount = ctx.amount("fraud_amount")
    seg_raw = ctx.raw.get("account_segment") or ""
    seg = seg_raw.strip().lower()

    if amount is None or seg not in ACCOUNT_CAPS:
        return None

    cap = ACCOUNT_CAPS[seg]
    customer_liability = min(0.5 * amount, cap)
    bank_compensation = amount - customer_liability
    return {
        "customer_liability": round(customer_liability, 2),
        "bank_compensation": round(bank_compensation, 2),
    }


def calc_unauth_customer_negligence(ctx: CompensationContext) -> Optional[Dict[str, float]]:
    """
    Unauthorised electronic transaction – customer negligence.
    Expects:
    - fraud_amount_before_report
    - fraud_amount_after_report
    """
    before_amt = ctx.amount("fraud_amount_before_report") or 0.0
    after_amt = ctx.amount("fraud_amount_after_report") or 0.0

    if before_amt == 0.0 and after_amt == 0.0:
        return None

    customer_liability = max(0.0, before_amt)
    bank_compensation = max(0.0, after_amt)
    return {
        "customer_liability": round(customer_liability, 2),
        "bank_compensation": round(bank_compensation, 2),
    }


def dispatch_compensation(
    data: Dict[str, Any],
    default_repo_rate: float,
    default_sb_rate: float,
) -> Dict[str, Any]:
    """
    Central dispatcher for the 10 high-priority scenarios.
    Returns:
      {
        "eligible": bool,
        "amount": Optional[float],
        "primary_amount": Optional[float],  # best 'transaction_amount' for response
        "primary_date": Optional[str],      # ISO string
        "customer_liability": Optional[float],
        "bank_compensation": Optional[float],
        "explanation": str,
      }
    """
    ctx = CompensationContext.from_llm(data)
    scen = ctx.scenario_type
    explanation_parts = [f"scenario_type={scen or 'none'}"]

    result: Dict[str, Any] = {
        "eligible": False,
        "amount": None,
        "primary_amount": None,
        "primary_date": None,
        "customer_liability": None,
        "bank_compensation": None,
        "explanation": "",
    }

    try:
        if scen == "upi":
            amt = ctx.amount("transaction_amount")
            comp = calc_upi_compensation(ctx)
            d = ctx.iso_date("transaction_date_iso")
            if comp is not None and amt is not None:
                result.update(
                    eligible=True,
                    amount=float(comp),
                    primary_amount=amt,
                    primary_date=d.isoformat() if d else None,
                )
                explanation_parts.append("calculator=upi")

        elif scen == "atm":
            amt = ctx.amount("transaction_amount")
            comp = calc_atm_compensation(ctx)
            d = ctx.iso_date("transaction_date_iso")
            if comp is not None and amt is not None:
                result.update(
                    eligible=True,
                    amount=float(comp),
                    primary_amount=amt,
                    primary_date=d.isoformat() if d else None,
                )
                explanation_parts.append("calculator=atm")

        elif scen == "neft":
            amt = ctx.amount("transaction_amount")
            comp = calc_neft_compensation(ctx, default_repo_rate=default_repo_rate)
            d = ctx.iso_date("due_date_iso")
            if comp is not None and amt is not None:
                result.update(
                    eligible=True,
                    amount=float(comp),
                    primary_amount=amt,
                    primary_date=d.isoformat() if d else None,
                )
                explanation_parts.append("calculator=neft")

        elif scen == "rtgs":
            amt = ctx.amount("transaction_amount")
            comp = calc_rtgs_compensation(ctx, default_repo_rate=default_repo_rate)
            d = ctx.iso_date("due_date_iso")
            if comp is not None and amt is not None:
                result.update(
                    eligible=True,
                    amount=float(comp),
                    primary_amount=amt,
                    primary_date=d.isoformat() if d else None,
                )
                explanation_parts.append("calculator=rtgs")

        elif scen == "cheque":
            amt = ctx.amount("transaction_amount")
            comp = calc_cheque_delay_compensation(ctx)
            d = ctx.iso_date("due_date_iso")
            if comp is not None and amt is not None:
                result.update(
                    eligible=True,
                    amount=float(comp),
                    primary_amount=amt,
                    primary_date=d.isoformat() if d else None,
                )
                explanation_parts.append("calculator=cheque_delay")

        elif scen == "nach_credit":
            amt = ctx.amount("transaction_amount")
            comp = calc_nach_credit_compensation(ctx)
            d = ctx.iso_date("due_date_iso")
            if comp is not None and amt is not None:
                result.update(
                    eligible=True,
                    amount=float(comp),
                    primary_amount=amt,
                    primary_date=d.isoformat() if d else None,
                )
                explanation_parts.append("calculator=nach_credit")

        elif scen == "nach_mandate":
            amt = ctx.amount("transaction_amount")
            comp = calc_nach_mandate_compensation(ctx)
            d = ctx.iso_date("revocation_effective_date_iso")
            if comp is not None and amt is not None:
                result.update(
                    eligible=True,
                    amount=float(comp),
                    primary_amount=amt,
                    primary_date=d.isoformat() if d else None,
                )
                explanation_parts.append("calculator=nach_mandate")

        elif scen == "unauth_zero":
            amt = ctx.amount("fraud_amount")
            comp = calc_unauth_zero_liability_interest(
                ctx, default_interest_rate=default_sb_rate
            )
            d = ctx.iso_date("debit_date_iso")
            if comp is not None and amt is not None:
                result.update(
                    eligible=True,
                    amount=float(comp),
                    primary_amount=amt,
                    primary_date=d.isoformat() if d else None,
                )
                explanation_parts.append("calculator=unauth_zero_interest")

        elif scen == "unauth_limited":
            amt = ctx.amount("fraud_amount")
            comp = calc_unauth_limited_liability(ctx)
            d = ctx.iso_date("debit_date_iso")
            if comp is not None and amt is not None:
                result.update(
                    eligible=True,
                    amount=float(comp["bank_compensation"]),
                    primary_amount=amt,
                    customer_liability=comp["customer_liability"],
                    bank_compensation=comp["bank_compensation"],
                    primary_date=d.isoformat() if d else None,
                )
                explanation_parts.append("calculator=unauth_limited_liability")

        elif scen == "unauth_negligence":
            comp = calc_unauth_customer_negligence(ctx)
            d = ctx.iso_date("debit_date_iso")
            if comp is not None:
                total_fraud = (
                    (ctx.amount("fraud_amount_before_report") or 0.0)
                    + (ctx.amount("fraud_amount_after_report") or 0.0)
                )
                result.update(
                    eligible=True,
                    amount=float(comp["bank_compensation"]),
                    primary_amount=total_fraud,
                    customer_liability=comp["customer_liability"],
                    bank_compensation=comp["bank_compensation"],
                    primary_date=d.isoformat() if d else None,
                )
                explanation_parts.append("calculator=unauth_customer_negligence")

    except Exception as exc:  # defensive guardrail
        explanation_parts.append(f"calculator_error={exc}")

    if not result["eligible"]:
        explanation_parts.append("eligible=False (missing or invalid fields)")

    result["explanation"] = "; ".join(explanation_parts)
    return result

