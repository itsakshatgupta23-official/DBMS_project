-- Chronicle – database/views.sql
-- Summary views for dashboard stats and expense analysis.
-- Run AFTER schema.sql (all tables must exist).

-- ─────────────────────────────────────────────────────────────
-- VIEW 1: member_expense_summary
-- Per-member breakdown inside each space:
--   total paid, total owed, and net balance (positive = owed money)
-- ─────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW member_expense_summary AS
SELECT
    sm.space_id,
    s.name                                              AS space_name,
    sm.user_id,
    u.username,
    sm.role,
    COALESCE(SUM(CASE WHEN e.paid_by = sm.user_id THEN e.amount ELSE 0 END), 0)
                                                        AS total_paid,
    COALESCE(SUM(es.share_amount), 0)                   AS total_owed,
    COALESCE(SUM(CASE WHEN e.paid_by = sm.user_id THEN e.amount ELSE 0 END), 0)
        - COALESCE(SUM(es.share_amount), 0)             AS net_balance
FROM space_members sm
JOIN spaces       s  ON s.space_id  = sm.space_id
JOIN users        u  ON u.user_id   = sm.user_id
LEFT JOIN expense_splits es
       ON es.user_id  = sm.user_id
LEFT JOIN expenses       e
       ON e.expense_id = es.expense_id
      AND e.space_id   = sm.space_id
GROUP BY sm.space_id, sm.user_id;


-- ─────────────────────────────────────────────────────────────
-- VIEW 2: space_dashboard_stats
-- One row per space with aggregated counts for quick dashboard rendering.
-- ─────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW space_dashboard_stats AS
SELECT
    s.space_id,
    s.name                                              AS space_name,
    s.space_type,
    s.invite_code,
    s.created_at,
    u.username                                          AS host_name,

    (SELECT COUNT(*) FROM space_members sm
     WHERE sm.space_id = s.space_id)                    AS member_count,

    (SELECT COUNT(*) FROM expenses e
     WHERE e.space_id = s.space_id)                     AS expense_count,

    (SELECT COALESCE(SUM(e2.amount), 0) FROM expenses e2
     WHERE e2.space_id = s.space_id)                    AS total_expense_amount,

    (SELECT COUNT(*) FROM chat_messages cm
     WHERE cm.space_id = s.space_id)                    AS message_count,

    (SELECT COUNT(*) FROM events ev
     WHERE ev.space_id = s.space_id)                    AS event_count,

    (SELECT COUNT(*) FROM media m
     WHERE m.space_id = s.space_id)                     AS media_count,

    (SELECT COUNT(*) FROM join_requests jr
     WHERE jr.space_id = s.space_id AND jr.status = 'PENDING')
                                                        AS pending_requests

FROM spaces s
JOIN users  u ON u.user_id = s.host_id;


-- ─────────────────────────────────────────────────────────────
-- VIEW 3: unsettled_debts
-- All outstanding settlement obligations with user names.
-- ─────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW unsettled_debts AS
SELECT
    st.settlement_id,
    st.space_id,
    sp.name                 AS space_name,
    st.from_user,
    fu.username             AS debtor,
    st.to_user,
    tu.username             AS creditor,
    st.amount,
    st.is_settled,
    st.settled_at
FROM settlements st
JOIN spaces sp ON sp.space_id = st.space_id
JOIN users  fu ON fu.user_id  = st.from_user
JOIN users  tu ON tu.user_id  = st.to_user
WHERE st.is_settled = FALSE;


-- ─────────────────────────────────────────────────────────────
-- VIEW 4: query_log_summary
-- Aggregated query performance per action label (for dev dashboard).
-- ─────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW query_log_summary AS
SELECT
    action_label,
    query_type,
    COUNT(*)                        AS total_calls,
    SUM(status = 'SUCCESS')         AS success_count,
    SUM(status = 'FAILED')          AS fail_count,
    ROUND(AVG(duration_ms), 2)      AS avg_ms,
    MAX(duration_ms)                AS max_ms,
    MIN(duration_ms)                AS min_ms,
    ROUND(AVG(rows_affected), 1)    AS avg_rows
FROM query_log
GROUP BY action_label, query_type
ORDER BY total_calls DESC;
