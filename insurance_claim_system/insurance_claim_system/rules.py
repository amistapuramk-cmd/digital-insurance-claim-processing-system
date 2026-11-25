"""Business rules for automatic claim validation."""
from datetime import date

AUTO_APPROVE_LIMIT = 5000.0   # claims at/below this (and clean) are auto-approved

def evaluate_claim(policy, amount, incident_date, already_claimed, duplicate_exists):
    """Returns (status, approved_amount, note, flag_reason)."""
    try:
        inc = date.fromisoformat(incident_date)
    except ValueError:
        return "Rejected", 0, "Invalid incident date.", None

    if not (date.fromisoformat(policy["start_date"]) <= inc <= date.fromisoformat(policy["end_date"])):
        return "Rejected", 0, "Incident date is outside the policy period.", None

    remaining = policy["coverage_amount"] - already_claimed
    if amount <= 0:
        return "Rejected", 0, "Claim amount must be positive.", None
    if amount > remaining:
        return "Under Review", 0, "Amount exceeds remaining coverage.", \
               f"Claim exceeds remaining coverage ({remaining:,.2f})."

    flags = []
    if duplicate_exists:
        flags.append("Possible duplicate claim (same policy & incident date).")
    if amount > 0.8 * policy["coverage_amount"]:
        flags.append("Amount is above 80% of total coverage.")
    if flags:
        return "Under Review", 0, "Flagged for manual review.", " ".join(flags)

    if amount <= AUTO_APPROVE_LIMIT:
        return "Approved", amount, "Auto-approved by system rules.", None
    return "Under Review", 0, "Sent to adjuster for review.", None
