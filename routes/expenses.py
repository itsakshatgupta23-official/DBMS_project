"""routes/expenses.py – Expense creation (equal & manual splits) + settlement"""
from flask import Blueprint, render_template, request, session, jsonify, abort
import db
from db import get_connection, commit, rollback
from utils.decorators import login_required, space_member_required
from utils.settlement import compute_settlements

expenses_bp = Blueprint("expenses", __name__, url_prefix="/spaces/<int:space_id>/expenses")

@expenses_bp.route("/")
@login_required
@space_member_required
def list_expenses(space_id):
    expenses = db.run_query(
        """SELECT e.*, u.username AS payer FROM expenses e
           JOIN users u ON u.user_id=e.paid_by
           WHERE e.space_id=%s ORDER BY e.created_at DESC""",
        (space_id,), action_label="LIST_EXPENSES", fetch="all"
    )
    members = db.run_query(
        "SELECT u.user_id, u.username FROM space_members sm JOIN users u ON u.user_id=sm.user_id WHERE sm.space_id=%s",
        (space_id,), action_label="EXPENSE_MEMBERS", fetch="all"
    )
    settlements = compute_settlements(space_id)
    space = db.run_query("SELECT * FROM spaces WHERE space_id=%s",(space_id,),fetch="one",action_label="EXPENSE_SPACE")
    role = db.run_query("SELECT role FROM space_members WHERE space_id=%s AND user_id=%s",(space_id,session["user_id"]),fetch="one",action_label="EXPENSE_ROLE")
    return render_template("space/expenses.html", expenses=expenses, members=members,
                           settlements=settlements, space=space, role=role["role"] if role else "MEMBER")

@expenses_bp.route("/add", methods=["POST"])
@login_required
@space_member_required
def add_expense(space_id):
    data        = request.get_json(silent=True) or {}
    description = data.get("description","").strip()
    amount      = float(data.get("amount",0))
    paid_by     = int(data.get("paid_by", session["user_id"]))
    split_type  = data.get("split_type","equal")  # "equal" | "manual"
    manual_splits = data.get("splits", {})  # {user_id: amount}

    if not description or amount <= 0:
        return jsonify({"error":"Invalid expense data."}), 400

    members = db.run_query(
        "SELECT user_id FROM space_members WHERE space_id=%s", (space_id,), action_label="EXPENSE_SPLIT_MEMBERS", fetch="all"
    )
    member_ids = [m["user_id"] for m in members]

    # ── Validate manual splits sum ──
    if split_type == "manual":
        total_manual = sum(float(v) for v in manual_splits.values())
        if abs(total_manual - amount) > 0.01:
            return jsonify({"error":f"Manual splits ({total_manual:.2f}) must equal total ({amount:.2f})."}), 400

    # ── Deduplicate rapid repeated submissions within 10 seconds ──
    recent = db.run_query(
        """SELECT expense_id FROM expenses 
           WHERE space_id = %s AND description = %s AND amount = %s AND paid_by = %s AND created_by = %s
           AND created_at >= NOW() - INTERVAL 10 SECOND""",
        (space_id, description, amount, paid_by, session["user_id"]),
        fetch="one", action_label="EXPENSE_DEDUP_CHECK"
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
            share = round(amount / len(member_ids), 2)
            for uid in member_ids:
                cursor.execute(
                    "INSERT INTO expense_splits (expense_id, user_id, share_amount) VALUES (%s,%s,%s)",
                    (expense_id, uid, share)
                )
        else:
            for uid_str, share in manual_splits.items():
                cursor.execute(
                    "INSERT INTO expense_splits (expense_id, user_id, share_amount) VALUES (%s,%s,%s)",
                    (expense_id, int(uid_str), float(share))
                )

        conn.commit()
        cursor.close()

        # Batch-notify all members in ONE round-trip (eliminates N+1 per-member INSERT loop)
        space = db.run_query(
            "SELECT name FROM spaces WHERE space_id=%s", (space_id,),
            fetch="one", action_label="EXPENSE_NOTIFY_SPACE"
        )
        notif_rows = [
            (uid, f"New expense '{description}' added in '{space['name']}'.")
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

@expenses_bp.route("/settlement/<int:settlement_id>/pay", methods=["POST"])
@login_required
def pay_settlement(space_id, settlement_id):
    row = db.run_query("SELECT * FROM settlements WHERE settlement_id=%s AND from_user=%s",
                       (settlement_id, session["user_id"]), fetch="one", action_label="SETTLE_CHECK")
    if not row:
        return jsonify({"error":"Settlement not found or unauthorized."}), 404
    db.run_query("UPDATE settlements SET is_settled=TRUE, settled_at=NOW() WHERE settlement_id=%s",
                 (settlement_id,), action_label="SETTLE_PAY", fetch="none")
    db.commit()
    return jsonify({"message":"Marked as paid."})
