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


def _parse_bool(value: Any) -> Optional[bool]:
    """
    Parse boolean-like LLM outputs.
    Accepts booleans or common strings like "true"/"false"/"yes"/"no".
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in {"true", "t", "yes", "y", "1"}:
        return True
    if s in {"false", "f", "no", "n", "0"}:
        return False
    return None


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

    def bool_field(self, key: str) -> Optional[bool]:
        return _parse_bool(self.raw.get(key))


def _calc_flat_per_day_beyond_tat(
    transaction_date: Optional[date],
    resolved_date: Optional[date],
    tat_days: int,
    per_day_comp: int = 100,
) -> Optional[int]:
    if not transaction_date or not resolved_date:
        return None
    total_delay = (resolved_date - transaction_date).days
    delay_beyond_tat = max(0, total_delay - tat_days)
    return delay_beyond_tat * per_day_comp


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


def calc_cir_credit_report_correction_delay(ctx: CompensationContext) -> Optional[float]:
    """
    CIR / Credit-Report Correction Delay:
    compensation = Rs100 per day beyond 30-day window.
    Expects:
    - dispute_filed_date_iso
    - resolved_date_iso (when corrected data sent / dispute resolved)
    """
    filed = ctx.iso_date("dispute_filed_date_iso")
    resolved = ctx.iso_date("resolved_date_iso")
    if not filed or not resolved:
        return None

    days_total = (resolved - filed).days
    delay_beyond_window = max(0, days_total - 30)
    return delay_beyond_window * 100.0


def calc_card_to_card_transfer_failure(ctx: CompensationContext) -> Optional[int]:
    """
    Card to Card Transfer Failure: Rs100 per day beyond T+1.
    Expects:
    - transaction_date_iso
    - resolved_date_iso
    - tat_days (optional; defaults to 1)
    """
    tat_days = ctx.int_field("tat_days") or 1
    txn_date = ctx.iso_date("transaction_date_iso")
    resolved_date = ctx.iso_date("resolved_date_iso")
    return _calc_flat_per_day_beyond_tat(txn_date, resolved_date, tat_days=tat_days, per_day_comp=100)


def calc_cheque_lost_in_transit(ctx: CompensationContext, default_sb_rate: float) -> Optional[float]:
    """
    Cheque Lost in Transit:
    Interest beyond TAT at cheque collection rate
    + interest for extra 15 days at SB rate
    + documented costs capped at Rs 250

    Expects:
    - transaction_amount (cheque amount)
    - transaction_date_iso (deposit/acceptance date)
    - credit_date_iso (when bank informs / actual credit)
    - cheque_collection_tat_days
    - cheque_collection_rate
    - interest_rate (SB rate) OR sb_rate (optional)
    - documented_costs_total
    """
    amount = ctx.amount("transaction_amount")
    deposit_date = ctx.iso_date("transaction_date_iso")
    credit_date = ctx.iso_date("credit_date_iso")
    tat_days = ctx.int_field("cheque_collection_tat_days")
    coll_rate = ctx.float_field("cheque_collection_rate")
    documented_costs = ctx.amount("documented_costs_total") if "documented_costs_total" in ctx.raw else ctx.float_field("documented_costs_total")
    # We reuse "interest_rate" as SB rate for this scenario.
    sb_rate = ctx.float_field("interest_rate") or ctx.float_field("sb_rate") or default_sb_rate

    if (
        amount is None
        or not deposit_date
        or not credit_date
        or tat_days is None
        or coll_rate is None
        or documented_costs is None
    ):
        return None

    if tat_days < 0:
        return None
    total_delay_days = (credit_date - deposit_date).days
    beyond_tat_days = max(0, total_delay_days - tat_days)
    if beyond_tat_days < 0:
        beyond_tat_days = 0

    interest_beyond_tat = amount * coll_rate * beyond_tat_days / 365.0
    interest_extra_15 = amount * sb_rate * 15 / 365.0
    costs_capped = min(250.0, max(0.0, float(documented_costs)))

    return round(interest_beyond_tat + interest_extra_15 + costs_capped, 2)


def calc_cheque_paid_after_stop_payment(ctx: CompensationContext, default_sb_rate: float) -> Optional[float]:
    """
    Cheque Paid After Stop-Payment:
    - reversal of cheque amount
    - value-dated credit to original debit date (approximate via SB-rate interest impact)
    - compensation for downstream charges/interest impact

    Expects:
    - transaction_amount (cheque amount)
    - transaction_date_iso (original debit date)
    - credit_date_iso (actual payment/value date when amount posted)
    - interest_rate (SB rate) OR sb_rate
    - downstream_charges_impact_total
    """
    cheque_amount = ctx.amount("transaction_amount")
    original_debit = ctx.iso_date("transaction_date_iso")
    payment_date = ctx.iso_date("credit_date_iso")
    downstream = ctx.amount("downstream_charges_impact_total")
    sb_rate = ctx.float_field("interest_rate") or ctx.float_field("sb_rate") or default_sb_rate

    if cheque_amount is None or not original_debit or not payment_date or downstream is None:
        return None

    days = (payment_date - original_debit).days
    days = max(0, days)
    value_date_interest_impact = cheque_amount * sb_rate * days / 365.0
    # Treat reversal of cheque amount as part of computed compensation, per guide text.
    return round(cheque_amount + value_date_interest_impact + downstream, 2)


def calc_credit_card_delayed_closure(ctx: CompensationContext) -> Optional[float]:
    """
    Credit Card - Delayed Closure:
    compensation = Rs500 per day beyond T+7 until actual closure.

    Expects:
    - delay_working_days_beyond_t_plus_7 (int)
    - outstanding_dues_present (bool) -> must be False
    """
    outstanding_dues_present = ctx.bool_field("outstanding_dues_present")
    delay_working_days = ctx.int_field("delay_working_days_beyond_t_plus_7")
    if outstanding_dues_present is not False:
        # If True or unclear, treat as not eligible.
        return None
    if delay_working_days is None or delay_working_days <= 0:
        return None
    return float(delay_working_days * 500)


def calc_credit_card_issued_without_consent(ctx: CompensationContext) -> Optional[float]:
    """
    Credit Card - Issued Without Consent:
    compensation = reversal of all charges + penalty = 2 × charges reversed

    Expects:
    - charges_reversed_total (float)
    - card_used (bool) -> must be False
    """
    card_used = ctx.bool_field("card_used")
    charges = ctx.amount("charges_reversed_total")
    if card_used is not False:
        return None
    if charges is None:
        return None
    return round(2 * charges, 2)


def calc_loan_security_docs_delay(ctx: CompensationContext) -> Optional[float]:
    """
    Delay in Return of Loan Security Docs:
    - Rs100 per week (or per day for premium products), subject to max cap.

    Expects:
    - delay_days_working_over_tat (int)
    - premium_product (bool)
    - cap_amount (float)
    """
    delay_days_working = ctx.int_field("delay_days_working_over_tat")
    premium_product = ctx.bool_field("premium_product")
    cap_amount = ctx.float_field("cap_amount")
    if delay_days_working is None or delay_days_working <= 0:
        return None
    if premium_product is None or cap_amount is None:
        return None

    if premium_product:
        comp = delay_days_working * 100
    else:
        # Convert working-day delay into week-equivalents (any partial week counts as a week).
        weeks = (delay_days_working + 6) // 7
        comp = weeks * 100
    return round(min(float(comp), float(cap_amount)), 2)


def calc_ecs_direct_debit_failed_execution(ctx: CompensationContext, default_sb_rate: float) -> Optional[float]:
    """
    ECS/Direct Debit - Failed/Delayed Execution:
    - interest at SB rate for delay period (min Rs100, max Rs1000 typical)
    - + customer penalties at other banks

    Expects:
    - transaction_amount
    - scheduled_date_iso
    - executed_date_iso
    - mandate_valid (bool) -> must be True
    - interest_rate (SB rate) OR sb_rate
    - customer_penalties_total
    """
    mandate_valid = ctx.bool_field("mandate_valid")
    if mandate_valid is not True:
        return None

    amount = ctx.amount("transaction_amount")
    scheduled = ctx.iso_date("scheduled_date_iso")
    executed = ctx.iso_date("executed_date_iso")
    customer_penalties = ctx.amount("customer_penalties_total") or 0.0
    sb_rate = ctx.float_field("interest_rate") or ctx.float_field("sb_rate") or default_sb_rate

    if amount is None or not scheduled or not executed or sb_rate is None:
        return None

    delay_days = (executed - scheduled).days
    if delay_days <= 0:
        return None

    interest = amount * sb_rate * delay_days / 365.0
    interest_clamped = min(1000.0, max(100.0, interest))
    return round(interest_clamped + float(customer_penalties), 2)


def calc_erroneous_debit_bank_error(ctx: CompensationContext) -> Optional[float]:
    """
    Erroneous Debit (Bank Error):
    - interest loss + downstream charges reversal
    - +1% in staff-fraud cases

    Expects:
    - interest_loss_amount
    - downstream_charges_reversal_amount
    - staff_fraud (bool)
    """
    interest_loss = ctx.amount("interest_loss_amount")
    downstream_reversal = ctx.amount("downstream_charges_reversal_amount")
    staff_fraud = ctx.bool_field("staff_fraud")

    if interest_loss is None or downstream_reversal is None or staff_fraud is None:
        return None

    base = float(interest_loss) + float(downstream_reversal)
    if staff_fraud is True:
        base += float(interest_loss) * 0.01
    return round(base, 2)


def calc_imps_failure(ctx: CompensationContext) -> Optional[int]:
    """
    Failed IMPS: Rs100 per day beyond T+1.
    Expects transaction_date_iso, resolved_date_iso, tat_days(optional; defaults to 1)
    """
    tat_days = ctx.int_field("tat_days") or 1
    txn_date = ctx.iso_date("transaction_date_iso")
    resolved_date = ctx.iso_date("resolved_date_iso")
    return _calc_flat_per_day_beyond_tat(txn_date, resolved_date, tat_days=tat_days, per_day_comp=100)


def calc_fixed_deposit_failed_action_maturity(ctx: CompensationContext) -> Optional[float]:
    """
    Fixed Deposit - Failed Action on Maturity Instruction:
    compensation = lost interest (intended vs actual) OR direct lost_interest_amount.

    Expects:
    - lost_interest_amount (preferred), OR:
      - intended_interest_amount
      - actual_interest_amount
    """
    lost = ctx.amount("lost_interest_amount")
    if lost is not None:
        return round(float(lost), 2)

    intended = ctx.amount("intended_interest_amount")
    actual = ctx.amount("actual_interest_amount")
    if intended is None or actual is None:
        return None

    diff = float(intended) - float(actual)
    if diff <= 0:
        return 0.0
    return round(diff, 2)


def calc_investment_redemption_slip_processing_delay(
    ctx: CompensationContext,
    default_repo_rate: float,
) -> Optional[float]:
    """
    Investment/Redemption Slip - Processing Delay (Mutual Fund, SGB):
    - Domestic SB rate interest for delayed period
    - For SGB rejection: Repo+2% for refund delay beyond T+1 working day

    Expects:
    - investment_amount
    - submission_date_iso
    - processing_date_iso (MF case)
    - interest_rate (SB rate) OR sb_rate
    - is_sgb_rejection (bool)
    - refund_delay_days_beyond_t_plus_1_working (int) (SGB case)
    - repo_rate (optional override) (SGB case)
    """
    is_sgb_rejection = ctx.bool_field("is_sgb_rejection")
    amount = ctx.amount("investment_amount")
    if amount is None or is_sgb_rejection is None:
        return None

    if is_sgb_rejection:
        delay_days = ctx.int_field("refund_delay_days_beyond_t_plus_1_working")
        repo_rate = ctx.float_field("repo_rate") or default_repo_rate
        if delay_days is None or delay_days <= 0:
            return None
        rate = repo_rate + 0.02
        return round(amount * rate * delay_days / 365.0, 2)

    # MF / non-SGB case
    submission_date = ctx.iso_date("submission_date_iso")
    processing_date = ctx.iso_date("processing_date_iso")
    sb_rate = ctx.float_field("interest_rate") or ctx.float_field("sb_rate")
    if not submission_date or not processing_date or sb_rate is None:
        return None

    delay_days = (processing_date - submission_date).days
    if delay_days <= 0:
        return 0.0
    return round(amount * sb_rate * delay_days / 365.0, 2)


def calc_duplicate_demand_draft_delay(ctx: CompensationContext) -> Optional[float]:
    """
    Issue of Duplicate Demand Draft - Delay:
    - Use FD rate for corresponding maturity period OR lump-sum per bank policy.

    Expects:
    - transaction_amount (DD amount)
    - request_date_iso
    - duplicate_issued_date_iso
    - fd_rate_corresponding_maturity (preferred), OR:
    - lump_sum_compensation_amount
    """
    lump = ctx.amount("lump_sum_compensation_amount")
    if lump is not None:
        return round(float(lump), 2)

    amount = ctx.amount("transaction_amount")
    request_date = ctx.iso_date("request_date_iso")
    duplicate_date = ctx.iso_date("duplicate_issued_date_iso")
    fd_rate = ctx.float_field("fd_rate_corresponding_maturity")
    if amount is None or not request_date or not duplicate_date or fd_rate is None:
        return None

    days = (duplicate_date - request_date).days
    days = max(0, days)
    if days == 0:
        return 0.0
    return round(amount * fd_rate * days / 365.0, 2)


def calc_locker_loss_bank_negligence(ctx: CompensationContext) -> Optional[float]:
    """
    Locker - Loss of Contents Due to Bank Negligence:
    compensation = 100 × annual locker rent, capped by cap_amount.

    Expects:
    - annual_locker_rent
    - cap_amount
    """
    rent = ctx.float_field("annual_locker_rent")
    cap = ctx.float_field("cap_amount")
    if rent is None or cap is None:
        return None
    raw = 100.0 * rent
    return round(min(raw, cap), 2)


def calc_bank_agent_violation(ctx: CompensationContext) -> Optional[float]:
    """
    Violation by Bank's Agent:
    compensation for actual direct financial loss (case-by-case).

    Expects:
    - actual_direct_financial_loss_amount
    """
    loss = ctx.amount("actual_direct_financial_loss_amount")
    if loss is None:
        return None
    return round(float(loss), 2)


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

        # ----------------------------
        # Remaining compensation types
        # ----------------------------
        elif scen == "cir_credit_report_correction_delay":
            comp = calc_cir_credit_report_correction_delay(ctx)
            if comp is not None:
                amt = ctx.amount("transaction_amount")
                resolved = ctx.iso_date("resolved_date_iso")
                result.update(
                    eligible=True,
                    amount=float(comp),
                    primary_amount=amt,
                    primary_date=resolved.isoformat() if resolved else None,
                )
                explanation_parts.append("calculator=cir_credit_report_correction_delay")

        elif scen == "card_to_card_transfer_failure":
            txn_amt = ctx.amount("transaction_amount")
            comp = calc_card_to_card_transfer_failure(ctx)
            if comp is not None:
                resolved = ctx.iso_date("resolved_date_iso")
                result.update(
                    eligible=True,
                    amount=float(comp),
                    primary_amount=txn_amt,
                    primary_date=resolved.isoformat() if resolved else None,
                )
                explanation_parts.append("calculator=card_to_card_transfer_failure")

        elif scen == "cheque_lost_in_transit":
            txn_amt = ctx.amount("transaction_amount")
            comp = calc_cheque_lost_in_transit(ctx, default_sb_rate=default_sb_rate)
            if comp is not None:
                credit_date = ctx.iso_date("credit_date_iso")
                result.update(
                    eligible=True,
                    amount=float(comp),
                    primary_amount=txn_amt,
                    primary_date=credit_date.isoformat() if credit_date else None,
                )
                explanation_parts.append("calculator=cheque_lost_in_transit")

        elif scen == "cheque_paid_after_stop_payment":
            txn_amt = ctx.amount("transaction_amount")
            comp = calc_cheque_paid_after_stop_payment(ctx, default_sb_rate=default_sb_rate)
            if comp is not None:
                payment_date = ctx.iso_date("credit_date_iso")
                result.update(
                    eligible=True,
                    amount=float(comp),
                    primary_amount=txn_amt,
                    primary_date=payment_date.isoformat() if payment_date else None,
                )
                explanation_parts.append("calculator=cheque_paid_after_stop_payment")

        elif scen == "credit_card_delayed_closure":
            comp = calc_credit_card_delayed_closure(ctx)
            if comp is not None:
                closure_actual = ctx.iso_date("closure_actual_date_iso")
                result.update(
                    eligible=True,
                    amount=float(comp),
                    primary_amount=ctx.amount("transaction_amount"),
                    primary_date=closure_actual.isoformat() if closure_actual else None,
                )
                explanation_parts.append("calculator=credit_card_delayed_closure")

        elif scen == "credit_card_issued_without_consent":
            comp = calc_credit_card_issued_without_consent(ctx)
            if comp is not None:
                closure_date = ctx.iso_date("transaction_date_iso")
                result.update(
                    eligible=True,
                    amount=float(comp),
                    primary_amount=ctx.amount("charges_reversed_total"),
                    primary_date=closure_date.isoformat() if closure_date else None,
                )
                explanation_parts.append("calculator=credit_card_issued_without_consent")

        elif scen == "loan_security_docs_delay":
            comp = calc_loan_security_docs_delay(ctx)
            if comp is not None:
                docs_returned = ctx.iso_date("docs_returned_date_iso")
                result.update(
                    eligible=True,
                    amount=float(comp),
                    primary_amount=ctx.amount("transaction_amount"),
                    primary_date=docs_returned.isoformat() if docs_returned else None,
                )
                explanation_parts.append("calculator=loan_security_docs_delay")

        elif scen == "ecs_direct_debit_failed_delayed_execution":
            comp = calc_ecs_direct_debit_failed_execution(ctx, default_sb_rate=default_sb_rate)
            if comp is not None:
                executed = ctx.iso_date("executed_date_iso")
                result.update(
                    eligible=True,
                    amount=float(comp),
                    primary_amount=ctx.amount("transaction_amount"),
                    primary_date=executed.isoformat() if executed else None,
                )
                explanation_parts.append("calculator=ecs_direct_debit_failed_delayed_execution")

        elif scen == "erroneous_debit_bank_error":
            comp = calc_erroneous_debit_bank_error(ctx)
            if comp is not None:
                resolved = ctx.iso_date("resolved_date_iso") or ctx.iso_date("reversal_date_iso")
                result.update(
                    eligible=True,
                    amount=float(comp),
                    primary_amount=ctx.amount("transaction_amount") or ctx.amount("interest_loss_amount"),
                    primary_date=resolved.isoformat() if resolved else None,
                )
                explanation_parts.append("calculator=erroneous_debit_bank_error")

        elif scen == "imps_failure":
            txn_amt = ctx.amount("transaction_amount")
            comp = calc_imps_failure(ctx)
            if comp is not None:
                resolved = ctx.iso_date("resolved_date_iso")
                result.update(
                    eligible=True,
                    amount=float(comp),
                    primary_amount=txn_amt,
                    primary_date=resolved.isoformat() if resolved else None,
                )
                explanation_parts.append("calculator=imps_failure")

        elif scen == "fixed_deposit_failed_action_maturity_instruction":
            comp = calc_fixed_deposit_failed_action_maturity(ctx)
            if comp is not None:
                result.update(
                    eligible=True,
                    amount=float(comp),
                    primary_amount=ctx.amount("transaction_amount"),
                    primary_date=ctx.iso_date("transaction_date_iso").isoformat() if ctx.iso_date("transaction_date_iso") else None,
                )
                explanation_parts.append("calculator=fixed_deposit_failed_action_maturity_instruction")

        elif scen == "investment_redemption_slip_processing_delay":
            comp = calc_investment_redemption_slip_processing_delay(ctx, default_repo_rate=default_repo_rate)
            if comp is not None:
                processing = ctx.iso_date("processing_date_iso")
                result.update(
                    eligible=True,
                    amount=float(comp),
                    primary_amount=ctx.amount("investment_amount") or ctx.amount("transaction_amount"),
                    primary_date=processing.isoformat() if processing else None,
                )
                explanation_parts.append("calculator=investment_redemption_slip_processing_delay")

        elif scen == "duplicate_demand_draft_delay":
            comp = calc_duplicate_demand_draft_delay(ctx)
            if comp is not None:
                dup_date = ctx.iso_date("duplicate_issued_date_iso")
                result.update(
                    eligible=True,
                    amount=float(comp),
                    primary_amount=ctx.amount("transaction_amount"),
                    primary_date=dup_date.isoformat() if dup_date else None,
                )
                explanation_parts.append("calculator=duplicate_demand_draft_delay")

        elif scen == "locker_loss_bank_negligence":
            comp = calc_locker_loss_bank_negligence(ctx)
            if comp is not None:
                result.update(
                    eligible=True,
                    amount=float(comp),
                    primary_amount=ctx.amount("annual_locker_rent"),
                    primary_date=ctx.iso_date("transaction_date_iso").isoformat() if ctx.iso_date("transaction_date_iso") else None,
                )
                explanation_parts.append("calculator=locker_loss_bank_negligence")

        elif scen == "bank_agent_violation":
            comp = calc_bank_agent_violation(ctx)
            if comp is not None:
                result.update(
                    eligible=True,
                    amount=float(comp),
                    primary_amount=comp,
                    primary_date=ctx.iso_date("transaction_date_iso").isoformat() if ctx.iso_date("transaction_date_iso") else None,
                )
                explanation_parts.append("calculator=bank_agent_violation")

    except Exception as exc:  # defensive guardrail
        explanation_parts.append(f"calculator_error={exc}")

    if not result["eligible"]:
        explanation_parts.append("eligible=False (missing or invalid fields)")

    result["explanation"] = "; ".join(explanation_parts)
    return result

