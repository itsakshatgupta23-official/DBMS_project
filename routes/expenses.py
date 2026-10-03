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
# Core Settlement & Expense Modification Handlers
# ──────────────────────────────────────────────────────────────

def process_settle_up(target_user_id: int, space_id: int = None):
    me = session.get("user_id")
    if not me:
        return jsonify({"error": "Unauthorized"}), 401

    if not target_user_id or int(target_user_id) == me:
        return jsonify({"error": "Invalid target user."}), 400

    target_user_id = int(target_user_id)

    if not space_id:
        shared = db.run_query(
            """SELECT sm1.space_id FROM space_members sm1
               JOIN space_members sm2 ON sm1.space_id = sm2.space_id
               WHERE sm1.user_id = %s AND sm2.user_id = %s
               LIMIT 1""",
            (me, target_user_id),
            fetch="one", action_label="SETTLE_FIND_SPACE"
        )
        if not shared:
            return jsonify({"error": "No shared space found with target user."}), 400
        space_id = shared["space_id"]
    else:
        space_id = int(space_id)
        mem = db.run_query(
            "SELECT 1 FROM space_members WHERE space_id=%s AND user_id=%s",
            (space_id, me), fetch="one", action_label="SETTLE_CHECK_MEM"
        )
        if not mem:
            return jsonify({"error": "You are not a member of this space."}), 403

    balances = _compute_pairwise_balances(space_id, me)
    net = round(balances.get(target_user_id, 0.0), 2)

    if abs(net) < 0.01:
        return jsonify({
            "success": True,
            "message": "Already settled up.",
            "net": 0.0,
            "status": "settled",
            "reload": True
        })

    target_user = db.run_query(
        "SELECT username FROM users WHERE user_id=%s",
        (target_user_id,), fetch="one", action_label="SETTLE_TARGET_USER"
    )
    target_name = target_user["username"] if target_user else f"User#{target_user_id}"

    abs_net = float(round(Decimal(str(abs(net))), 2))

    if net > 0:
        # Target user owes current user money. Target user pays current user.
        payer = target_user_id
        recipient = me
    else:
        # Current user owes target user money. Current user pays target user.
        payer = me
        recipient = target_user_id

    desc = f"Settlement with {target_name}"

    conn = get_connection()
    try:
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """INSERT INTO expenses (space_id, description, amount, paid_by, created_by)
               VALUES (%s, %s, %s, %s, %s)""",
            (space_id, desc, abs_net, payer, me)
        )
        expense_id = cursor.lastrowid

        # Insert pairwise settlement splits
        cursor.execute(
            """INSERT INTO expense_splits (expense_id, user_id, share_amount)
               VALUES (%s, %s, %s)""",
            (expense_id, payer, 0.00)
        )
        cursor.execute(
            """INSERT INTO expense_splits (expense_id, user_id, share_amount)
               VALUES (%s, %s, %s)""",
            (expense_id, recipient, abs_net)
        )

        conn.commit()
        cursor.close()

        # Recalculate net balance
        new_balances = _compute_pairwise_balances(space_id, me)
        new_net = round(new_balances.get(target_user_id, 0.0), 2)

        return jsonify({
            "success": True,
            "message": f"Settled up with {target_name} successfully!",
            "net": new_net,
            "status": "settled",
            "expense_id": expense_id,
            "reload": True
        })
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500


def process_delete_expense(expense_id: int):
    me = session.get("user_id")
    if not me:
        return jsonify({"error": "Unauthorized"}), 401

    exp = db.run_query(
        "SELECT expense_id, space_id, paid_by, created_by FROM expenses WHERE expense_id = %s",
        (expense_id,), fetch="one", action_label="EXPENSE_FETCH_DEL"
    )
    if not exp:
        return jsonify({"error": "Expense not found."}), 404

    is_split_user = db.run_query(
        "SELECT 1 FROM expense_splits WHERE expense_id = %s AND user_id = %s",
        (expense_id, me), fetch="one", action_label="EXPENSE_CHECK_SPLIT_DEL"
    )

    is_participant = (
        exp["paid_by"] == me or 
        exp["created_by"] == me or 
        bool(is_split_user)
    )

    if not is_participant:
        return jsonify({"error": "Unauthorized. Only participants in this expense can delete it."}), 403

    conn = get_connection()
    try:
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("DELETE FROM expense_splits WHERE expense_id = %s", (expense_id,))
        cursor.execute("DELETE FROM expenses WHERE expense_id = %s", (expense_id,))

        conn.commit()
        cursor.close()

        return jsonify({"success": True, "message": "Expense deleted successfully.", "reload": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500


def process_edit_expense(expense_id: int):
    me = session.get("user_id")
    if not me:
        return jsonify({"error": "Unauthorized"}), 401

    exp = db.run_query(
        "SELECT expense_id, space_id, description, amount, paid_by, created_by FROM expenses WHERE expense_id = %s",
        (expense_id,), fetch="one", action_label="EXPENSE_FETCH_EDIT"
    )
    if not exp:
        return jsonify({"error": "Expense not found."}), 404

    is_split_user = db.run_query(
        "SELECT 1 FROM expense_splits WHERE expense_id = %s AND user_id = %s",
        (expense_id, me), fetch="one", action_label="EXPENSE_CHECK_SPLIT_EDIT"
    )

    is_participant = (
        exp["paid_by"] == me or 
        exp["created_by"] == me or 
        bool(is_split_user)
    )

    if not is_participant:
        return jsonify({"error": "Unauthorized. Only participants in this expense can edit it."}), 403

    data = request.get_json(silent=True) or request.form.to_dict() or {}
    new_desc = (data.get("description") or "").strip()
    amount_val = data.get("amount")

    if not new_desc:
        return jsonify({"error": "Description is required."}), 400

    try:
        new_amount = round(float(amount_val), 2)
        if new_amount <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        return jsonify({"error": "Valid positive amount is required."}), 400

    new_paid_by = data.get("paid_by")
    if new_paid_by:
        try:
            new_paid_by = int(new_paid_by)
        except (ValueError, TypeError):
            new_paid_by = exp["paid_by"]
    else:
        new_paid_by = exp["paid_by"]

    manual_splits = data.get("splits")

    conn = get_connection()
    try:
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "UPDATE expenses SET description = %s, amount = %s, paid_by = %s WHERE expense_id = %s",
            (new_desc, new_amount, new_paid_by, expense_id)
        )

        if manual_splits and isinstance(manual_splits, dict):
            total_manual = sum(float(v) for v in manual_splits.values())
            if abs(total_manual - new_amount) > 0.05:
                conn.rollback()
                cursor.close()
                return jsonify({"error": f"Manual splits ({total_manual:.2f}) must equal amount ({new_amount:.2f})."}), 400

            cursor.execute("DELETE FROM expense_splits WHERE expense_id = %s", (expense_id,))
            for uid_str, share_val in manual_splits.items():
                cursor.execute(
                    "INSERT INTO expense_splits (expense_id, user_id, share_amount) VALUES (%s, %s, %s)",
                    (expense_id, int(uid_str), round(float(share_val), 2))
                )
        else:
            cursor.execute(
                "SELECT user_id, share_amount FROM expense_splits WHERE expense_id = %s ORDER BY user_id",
                (expense_id,)
            )
            old_splits = cursor.fetchall()
            old_total = sum(float(s["share_amount"]) for s in old_splits)

            if old_splits:
                n = len(old_splits)
                if old_total > 0 and abs(old_total - float(exp["amount"])) < 0.05:
                    first_share = float(old_splits[0]["share_amount"])
                    is_equal = all(abs(float(s["share_amount"]) - first_share) <= 0.02 for s in old_splits)

                    if is_equal:
                        base_share = round(new_amount / n, 2)
                        for i, s in enumerate(old_splits):
                            share = round(new_amount - base_share * (n - 1), 2) if i == n - 1 else base_share
                            cursor.execute(
                                "UPDATE expense_splits SET share_amount = %s WHERE expense_id = %s AND user_id = %s",
                                (share, expense_id, s["user_id"])
                            )
                    else:
                        running_sum = 0.0
                        for i, s in enumerate(old_splits):
                            if i == n - 1:
                                share = round(new_amount - running_sum, 2)
                            else:
                                ratio = float(s["share_amount"]) / old_total
                                share = round(new_amount * ratio, 2)
                                running_sum += share
                            cursor.execute(
                                "UPDATE expense_splits SET share_amount = %s WHERE expense_id = %s AND user_id = %s",
                                (share, expense_id, s["user_id"])
                            )
                else:
                    base_share = round(new_amount / n, 2)
                    for i, s in enumerate(old_splits):
                        share = round(new_amount - base_share * (n - 1), 2) if i == n - 1 else base_share
                        cursor.execute(
                            "UPDATE expense_splits SET share_amount = %s WHERE expense_id = %s AND user_id = %s",
                            (share, expense_id, s["user_id"])
                        )

        conn.commit()
        cursor.close()

        return jsonify({"success": True, "message": "Expense updated successfully.", "reload": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500


# ── Blueprint Routes ──────────────────────────────────────────

@expenses_bp.route("/settle-up", methods=["POST"])
@login_required
@space_member_required
def settle_up_space(space_id):
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    target_user_id = data.get("target_user_id") or request.args.get("target_user_id")
    return process_settle_up(target_user_id, space_id)


@expenses_bp.route("/settle-up/<int:other_uid>", methods=["POST"])
@login_required
@space_member_required
def settle_up_legacy(space_id, other_uid):
    return process_settle_up(other_uid, space_id)


@expenses_bp.route("/delete-expense/<int:expense_id>", methods=["POST", "DELETE"])
@login_required
@space_member_required
def delete_expense_space(space_id, expense_id):
    return process_delete_expense(expense_id)


@expenses_bp.route("/edit-expense/<int:expense_id>", methods=["POST"])
@login_required
@space_member_required
def edit_expense_space(space_id, expense_id):
    return process_edit_expense(expense_id)


# ── Direct Endpoints (for root URL mapping) ───────────────────

def settle_up_endpoint():
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    target_user_id = data.get("target_user_id") or request.args.get("target_user_id")
    space_id = data.get("space_id") or request.args.get("space_id")
    return process_settle_up(target_user_id, space_id)


def delete_expense_endpoint(expense_id: int):
    return process_delete_expense(expense_id)


def edit_expense_endpoint(expense_id: int):
    return process_edit_expense(expense_id)

