"""
utils/settlement.py – Greedy debt settlement algorithm.
Computes minimal transactions needed to clear all balances in a space.
"""

import db
from decimal import Decimal


def compute_settlements(space_id: int) -> list[dict]:
    """
    1. For each member: net = total_paid - total_share_owed
    2. Use two-pointer greedy on sorted creditors / debtors
    3. Persist / return settlement rows
    """
    # Fetch all expense splits for the space with payer info
    rows = db.run_query(
        """
        SELECT es.user_id, es.share_amount, e.paid_by, e.amount AS total_amount
        FROM   expense_splits es
        JOIN   expenses e ON e.expense_id = es.expense_id
        WHERE  e.space_id = %s
        """,
        (space_id,),
        action_label="SETTLEMENT_COMPUTE",
        fetch="all",
    )

    # net[user_id] = amount_paid - amount_owed
    net: dict[int, Decimal] = {}
    for row in rows:
        uid     = row["user_id"]
        paid_by = row["paid_by"]
        share   = Decimal(str(row["share_amount"]))
        paid    = Decimal(str(row["total_amount"])) if uid == paid_by else Decimal("0")

        net[uid]     = net.get(uid,     Decimal("0")) + paid - share
        net[paid_by] = net.get(paid_by, Decimal("0"))  # ensure key exists

    # Separate creditors (positive) and debtors (negative)
    creditors = sorted([(uid, amt) for uid, amt in net.items() if amt > 0],  key=lambda x: -x[1])
    debtors   = sorted([(uid, amt) for uid, amt in net.items() if amt < 0],  key=lambda x: x[1])

    settlements = []
    ci, di = 0, 0
    while ci < len(creditors) and di < len(debtors):
        c_uid, c_amt = creditors[ci]
        d_uid, d_amt = debtors[di]
        transfer = min(c_amt, -d_amt)

        settlements.append({
            "from_user": d_uid,
            "to_user":   c_uid,
            "amount":    float(round(transfer, 2)),
        })

        creditors[ci] = (c_uid, c_amt - transfer)
        debtors[di]   = (d_uid, d_amt + transfer)

        if creditors[ci][1] == 0:
            ci += 1
        if debtors[di][1] == 0:
            di += 1

    # Fetch existing unsettled rows to avoid duplicates
    existing = db.run_query(
        "SELECT from_user, to_user, amount FROM settlements WHERE space_id=%s AND is_settled=FALSE",
        (space_id,), action_label="SETTLEMENT_EXISTING", fetch="all"
    )
    existing_set = {(r["from_user"], r["to_user"]) for r in existing}

    # Persist new settlements
    for s in settlements:
        if (s["from_user"], s["to_user"]) not in existing_set and s["amount"] > 0:
            db.run_query(
                "INSERT INTO settlements (space_id, from_user, to_user, amount) VALUES (%s,%s,%s,%s)",
                (space_id, s["from_user"], s["to_user"], s["amount"]),
                action_label="SETTLEMENT_INSERT", fetch="none"
            )
    db.commit()

    # Return all unsettled settlements with usernames
    result = db.run_query(
        """
        SELECT s.settlement_id, s.from_user, s.to_user, s.amount,
               fu.username AS from_name, tu.username AS to_name
        FROM   settlements s
        JOIN   users fu ON fu.user_id = s.from_user
        JOIN   users tu ON tu.user_id = s.to_user
        WHERE  s.space_id = %s AND s.is_settled = FALSE
        ORDER  BY s.amount DESC
        """,
        (space_id,), action_label="SETTLEMENT_FETCH_RESULT", fetch="all"
    )
    return result
