-- Chronicle – Performance Indexes (MySQL 8 compatible)
-- Uses ALTER TABLE ... ADD INDEX which silently handles duplicates via errno 1061 in init_db.py.

-- Expenses: filter by space
ALTER TABLE expenses      ADD INDEX idx_expenses_space          (space_id);

-- Expense splits: join to expense
ALTER TABLE expense_splits ADD INDEX idx_expense_splits_expense (expense_id);

-- Expense splits: user-level lookup (member_expense_summary view)
ALTER TABLE expense_splits ADD INDEX idx_expense_splits_user    (user_id);

-- Chat messages: timeline fetch per space (cursor on message_id)
ALTER TABLE chat_messages  ADD INDEX idx_chat_space             (space_id, message_id);

-- Space members: primary access-control lookup (decorator on every request)
ALTER TABLE space_members  ADD INDEX idx_space_members_lookup   (space_id, user_id);

-- Media access: permission check per media item and user
ALTER TABLE media_access   ADD INDEX idx_media_access_lookup    (media_id, user_id);

-- Media: space gallery listing
ALTER TABLE media          ADD INDEX idx_media_space            (space_id, uploaded_at);

-- Join requests: pending count for badge polling and host modal
ALTER TABLE join_requests  ADD INDEX idx_join_req_space_status  (space_id, status);

-- Notifications: unread badge count and list
ALTER TABLE notifications  ADD INDEX idx_notifications_user_read (user_id, is_read);

-- Private messages: poll cursor (conversation_id + message_id)
ALTER TABLE private_messages ADD INDEX idx_private_messages_conv (conversation_id, message_id);

-- Settlements: unsettled lookup per space (used by compute_settlements)
ALTER TABLE settlements    ADD INDEX idx_settlements_space_settled (space_id, is_settled);

-- Events: chronological listing per space
ALTER TABLE events         ADD INDEX idx_events_space           (space_id, event_date);

-- Resources: listing per space
ALTER TABLE resources      ADD INDEX idx_resources_space        (space_id);

-- Notes: listing per space
ALTER TABLE notes          ADD INDEX idx_notes_space            (space_id, updated_at);
ALTER TABLE notes          ADD INDEX idx_notes_source_msg       (source_message_id);

-- Chat: pinned messages
ALTER TABLE chat_messages  ADD INDEX idx_chat_space_pinned      (space_id, is_pinned);

-- Query log: dev dashboard filter by created_at
ALTER TABLE query_log      ADD INDEX idx_query_log_created      (created_at);

-- Query log: filter by action_label for summary view
ALTER TABLE query_log      ADD INDEX idx_query_log_action       (action_label);
