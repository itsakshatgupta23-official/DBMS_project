"""routes/expenses.py – Splitwise-style P2P expense sharing & settlement"""
from decimal import Decimal
from flask import Blueprint, render_template, request, session, jsonify
import db
from db import get_connection
from utils.decorators import login_required, space_member_required

expenses_bp = Blueprint("expenses", __name__, url_prefix="/spaces/<int:space_id>/expenses")


# ──────────────────────────────────────────────────────────────
# Helper: compute pairwise net balances (positive = they owe you)
# ──────────────────────────────────────────────────────────────
def _compute_pairwise_balances(space_id: int, current_user_id: int) -> dict:
    """
    Returns a dict keyed by other_user_id:
      net > 0  → that person owes current_user net amount
      net < 0  → current_user owes that person abs(net) amount
      net == 0 → settled

    Algorithm:
      For every expense E in the space:
        payer = E.paid_by
        For every split row (user_id, share_amount) in E:
          if payer == current_user and user_id != current_user:
              # current_user lent share_amount to user_id
              balances[user_id] += share_amount
          if user_id == current_user and payer != current_user:
              # current_user borrowed share_amount from payer
              balances[payer] -= share_amount
    """
    rows = db.run_query(
        """
        SELECT e.expense_id, e.paid_by,
               es.user_id   AS split_user,
               es.share_amount
        FROM   expenses e
        JOIN   expense_splits es ON es.expense_id = e.expense_id
        WHERE  e.space_id = %s
        """,
        (space_id,),
        action_label="PAIRWISE_BALANCE_FETCH",
        fetch="all",
    )

    balances: dict[int, Decimal] = {}
    for row in rows:
        payer      = row["paid_by"]
        split_user = row["split_user"]
        share      = Decimal(str(row["share_amount"]))

        if payer == current_user_id and split_user != current_user_id:
            # I paid → they owe me
            balances[split_user] = balances.get(split_user, Decimal("0")) + share

        elif split_user == current_user_id and payer != current_user_id:
            # They paid → I owe them
            balances[payer] = balances.get(payer, Decimal("0")) - share

    return {uid: float(round(amt, 2)) for uid, amt in balances.items()}


# ──────────────────────────────────────────────────────────────
# GET  /spaces/<id>/expenses/
# ──────────────────────────────────────────────────────────────
@expenses_bp.route("/")
@login_required
@space_member_required
def list_expenses(space_id):
    me = session["user_id"]

    # All members in space
    members = db.run_query(
        """SELECT u.user_id, u.username
           FROM space_members sm
           JOIN users u ON u.user_id = sm.user_id
           WHERE sm.space_id = %s""",
        (space_id,), action_label="EXPENSE_MEMBERS", fetch="all"
    )

    # Build member lookup map
    member_map = {m["user_id"]: m["username"] for m in members}

    # Pairwise net balances for current user
    raw_balances = _compute_pairwise_balances(space_id, me)

    # Build structured member_balances list (exclude self)
    member_balances = []
    total_owe  = 0.0   # sum of negatives (I owe others)
    total_owed = 0.0   # sum of positives (others owe me)

    for uid, net in raw_balances.items():
        if uid == me:
            continue
        username = member_map.get(uid, f"User#{uid}")
        if net > 0.005:
            status = "owed"         # they owe me
            total_owed += net
        elif net < -0.005:
            status = "owe"          # I owe them
            total_owe += abs(net)
        else:
            net    = 0.0
            status = "settled"

        member_balances.append({
            "user_id":  uid,
            "username": username,
            "net":      net,
            "status":   status,
        })

    # Members with zero activity (no shared expense) → settled
    for m in members:
        uid = m["user_id"]
        if uid == me or uid in raw_balances:
            continue
        member_balances.append({
            "user_id":  uid,
            "username": m["username"],
            "net":      0.0,
            "status":   "settled",
        })

    # Sort: owe first, then owed, then settled
    order = {"owe": 0, "owed": 1, "settled": 2}
    member_balances.sort(key=lambda x: (order[x["status"]], -abs(x["net"])))

    # Space & role info
    space = db.run_query(
        "SELECT space_id, name, description, space_type, invite_code FROM spaces WHERE space_id=%s",
        (space_id,), fetch="one", action_label="EXPENSE_SPACE"
    )
    role = db.run_query(
        "SELECT role FROM space_members WHERE space_id=%s AND user_id=%s",
        (space_id, me), fetch="one", action_label="EXPENSE_ROLE"
    )

    return render_template(
        "space/expenses.html",
        members=members,
        member_map=member_map,
        member_balances=member_balances,
        total_owe=round(total_owe, 2),
        total_owed=round(total_owed, 2),
        space=space,
        role=role["role"] if role else "MEMBER",
    )


# ──────────────────────────────────────────────────────────────
# GET  /spaces/<id>/expenses/history/<other_uid>
#      Returns JSON transaction history between me & other_uid
# ──────────────────────────────────────────────────────────────
@expenses_bp.route("/history/<int:other_uid>")
@login_required
@space_member_required
def pairwise_history(space_id, other_uid):
    me = session["user_id"]

    # All expenses involving BOTH me and other_uid
    rows = db.run_query(
        """
        SELECT e.expense_id, e.description, e.amount, e.paid_by,
               e.created_at, u.username AS payer_name,
               es_me.share_amount   AS my_share,
               es_oth.share_amount  AS their_share
        FROM   expenses e
        JOIN   users u ON u.user_id = e.paid_by
        JOIN   expense_splits es_me  ON es_me.expense_id  = e.expense_id  AND es_me.user_id  = %s
        JOIN   expense_splits es_oth ON es_oth.expense_id = e.expense_id  AND es_oth.user_id = %s
        WHERE  e.space_id = %s
        ORDER  BY e.created_at DESC
        """,
        (me, other_uid, space_id),
        action_label="PAIRWISE_HISTORY",
        fetch="all",
    )

    history = []
    for r in rows:
        paid_by    = r["paid_by"]
        my_share   = float(r["my_share"]   or 0)
        their_share= float(r["their_share"] or 0)

        if paid_by == me:
            # I paid → I lent them their_share
            role_label = "you_paid"
            your_amount = their_share
        else:
            # They paid → I borrowed my_share
            role_label = "they_paid"
            your_amount = my_share

        history.append({
            "expense_id":   r["expense_id"],
            "description":  r["description"],
            "total_amount": float(r["amount"]),
            "paid_by":      paid_by,
            "payer_name":   r["payer_name"],
            "my_share":     my_share,
            "their_share":  their_share,
            "your_amount":  round(your_amount, 2),
            "role":         role_label,
            "date":         r["created_at"].strftime("%d %b %Y") if r["created_at"] else "",
        })

    # Other user info
    other = db.run_query(
        "SELECT user_id, username FROM users WHERE user_id=%s",
        (other_uid,), fetch="one", action_label="PAIRWISE_OTHER_USER"
    )

    # Current net balance between me and other_uid
    balances = _compute_pairwise_balances(space_id, me)
    net = round(balances.get(other_uid, 0.0), 2)

    return jsonify({
        "other_user": {"user_id": other_uid, "username": other["username"] if other else ""},
        "net":        net,
        "history":    history,
    })


# ──────────────────────────────────────────────────────────────
# POST /spaces/<id>/expenses/add
# ──────────────────────────────────────────────────────────────
@expenses_bp.route("/add", methods=["POST"])
@login_required
@space_member_required
def add_expense(space_id):
    data          = request.get_json(silent=True) or {}
    description   = data.get("description", "").strip()
    amount        = float(data.get("amount", 0))
    paid_by       = int(data.get("paid_by", session["user_id"]))
    split_type    = data.get("split_type", "equal")   # "equal" | "manual"
    manual_splits = data.get("splits", {})             # {str(user_id): amount}
    split_among   = data.get("split_among", [])        # list of user_ids for equal split

    if not description or amount <= 0:
        return jsonify({"error": "Invalid expense data."}), 400

    # Resolve split member IDs
    if split_type == "equal":
        if split_among:
            member_ids = [int(uid) for uid in split_among]
        else:
            all_members = db.run_query(
                "SELECT user_id FROM space_members WHERE space_id=%s",
                (space_id,), action_label="EXPENSE_ALL_MEMBERS", fetch="all"
            )
            member_ids = [m["user_id"] for m in all_members]
    else:
        member_ids = [int(k) for k in manual_splits.keys()]

    if not member_ids:
        return jsonify({"error": "No members selected for split."}), 400

    # Validate manual splits
    if split_type == "manual":
        total_manual = sum(float(v) for v in manual_splits.values())
        if abs(total_manual - amount) > 0.01:
            return jsonify({"error": f"Manual splits ({total_manual:.2f}) must equal total ({amount:.2f})."}), 400

    # Deduplication guard (10-second window)
    recent = db.run_query(
        """SELECT expense_id FROM expenses
           WHERE space_id = %s AND description = %s AND amount = %s
             AND paid_by = %s AND created_by = %s
             AND created_at >= NOW() - INTERVAL 10 SECOND""",
        (space_id, description, amount, paid_by, session["user_id"]),
        fetch="one", action_label="EXPENSE_DEDUP"
    )
    if recent:
        return jsonify({"message": "Expense already recorded.", "reload": True})

    conn = get_connection()
    try:
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "INSERT INTO expenses (space_id, description, amount, paid_by, created_by) VALUES (%s,%s,%s,%s,%s)",
            (space_id, description, amount, paid_by, session["user_id"])
        )
        expense_id = cursor.lastrowid

        if split_type == "equal":
            n     = len(member_ids)
            share = round(amount / n, 2)
            for i, uid in enumerate(member_ids):
                actual_share = round(amount - share * (n - 1), 2) if i == n - 1 else share
                cursor.execute(
                    "INSERT INTO expense_splits (expense_id, user_id, share_amount) VALUES (%s,%s,%s)",
                    (expense_id, uid, actual_share)
                )
        else:
            for uid_str, share_val in manual_splits.items():
                cursor.execute(
                    "INSERT INTO expense_splits (expense_id, user_id, share_amount) VALUES (%s,%s,%s)",
                    (expense_id, int(uid_str), float(share_val))
                )

        conn.commit()
        cursor.close()

        # Batch notifications
        space_row = db.run_query(
            "SELECT name FROM spaces WHERE space_id=%s",
            (space_id,), fetch="one", action_label="EXPENSE_NOTIFY_SPACE"
        )
        notif_rows = [
            (uid, f"New expense '{description}' added in '{space_row['name']}'.")
            for uid in member_ids
            if uid != session["user_id"]
        ]
        if notif_rows:
            notif_cur = db.get_db().cursor()
            notif_cur.executemany(
                "INSERT INTO notifications (user_id, message) VALUES (%s, %s)",
                notif_rows
            )
            notif_cur.close()

        return jsonify({"message": "Expense added successfully.", "reload": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────────────────────
# POST /spaces/<id>/expenses/settle-up/<other_uid>
#      "Settle Up" action — marks net balance as 0 by inserting
#      a settlement record and a counter-expense split record.
# ──────────────────────────────────────────────────────────────
@expenses_bp.route("/settle-up/<int:other_uid>", methods=["POST"])
@login_required
@space_member_required
def settle_up(space_id, other_uid):
    me = session["user_id"]

    balances = _compute_pairwise_balances(space_id, me)
    net = round(balances.get(other_uid, 0.0), 2)

    if abs(net) < 0.01:
        return jsonify({"message": "Already settled.", "reload": True})

    if net > 0:
        # They owe me — I'm forgiving (or they paid me back)
        from_user, to_user, amount = other_uid, me, net
    else:
        # I owe them — I'm paying
        from_user, to_user, amount = me, other_uid, abs(net)

    # Mark any existing unsettled settlements between these two as settled
    db.run_query(
        """UPDATE settlements SET is_settled=TRUE, settled_at=NOW()
           WHERE space_id=%s AND (
             (from_user=%s AND to_user=%s) OR (from_user=%s AND to_user=%s)
           ) AND is_settled=FALSE""",
        (space_id, from_user, to_user, to_user, from_user),
        fetch="none", action_label="SETTLE_UP_MARK"
    )

    # Insert a fresh settled settlement so the history is clean
    db.run_query(
        """INSERT INTO settlements (space_id, from_user, to_user, amount, is_settled, settled_at)
           VALUES (%s,%s,%s,%s,TRUE,NOW())""",
        (space_id, from_user, to_user, amount),
        fetch="none", action_label="SETTLE_UP_INSERT"
    )
    db.commit()

    return jsonify({"message": "Settled up successfully.", "reload": True})
