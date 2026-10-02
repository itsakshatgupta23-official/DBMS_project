-- Chronicle - Complete Database Schema
-- Run once - all statements are idempotent (IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS users (
    user_id       INT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(50)  NOT NULL UNIQUE,
    email         VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_developer  BOOLEAN DEFAULT FALSE,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS spaces (
    space_id    INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    description TEXT,
    space_type  ENUM('Trip','Hostel','College Event','Party','Family Event','Project Group','Other') DEFAULT 'Trip',
    invite_code VARCHAR(10)  NOT NULL UNIQUE,
    host_id     INT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (host_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS space_members (
    space_id  INT NOT NULL,
    user_id   INT NOT NULL,
    role      ENUM('HOST','MEMBER') DEFAULT 'MEMBER',
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (space_id, user_id),
    FOREIGN KEY (space_id) REFERENCES spaces(space_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id)  REFERENCES users(user_id)  ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS join_requests (
    request_id   INT AUTO_INCREMENT PRIMARY KEY,
    space_id     INT NOT NULL,
    user_id      INT NOT NULL,
    status       ENUM('PENDING','APPROVED','REJECTED') DEFAULT 'PENDING',
    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    decided_at   TIMESTAMP NULL,
    decided_by   INT NULL,
    FOREIGN KEY (space_id)   REFERENCES spaces(space_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id)    REFERENCES users(user_id)   ON DELETE CASCADE,
    FOREIGN KEY (decided_by) REFERENCES users(user_id)   ON DELETE SET NULL,
    CONSTRAINT unique_pending_req UNIQUE (space_id, user_id, status)
);

CREATE TABLE IF NOT EXISTS expenses (
    expense_id  INT AUTO_INCREMENT PRIMARY KEY,
    space_id    INT NOT NULL,
    description VARCHAR(255) NOT NULL,
    amount      DECIMAL(10,2) NOT NULL CHECK (amount > 0),
    paid_by     INT NOT NULL,
    created_by  INT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (space_id)   REFERENCES spaces(space_id) ON DELETE CASCADE,
    FOREIGN KEY (paid_by)    REFERENCES users(user_id)   ON DELETE CASCADE,
    FOREIGN KEY (created_by) REFERENCES users(user_id)   ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS expense_splits (
    expense_id   INT NOT NULL,
    user_id      INT NOT NULL,
    share_amount DECIMAL(10,2) NOT NULL CHECK (share_amount >= 0),
    PRIMARY KEY (expense_id, user_id),
    FOREIGN KEY (expense_id) REFERENCES expenses(expense_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id)    REFERENCES users(user_id)       ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS settlements (
    settlement_id INT AUTO_INCREMENT PRIMARY KEY,
    space_id      INT NOT NULL,
    from_user     INT NOT NULL,
    to_user       INT NOT NULL,
    amount        DECIMAL(10,2) NOT NULL CHECK (amount > 0),
    is_settled    BOOLEAN DEFAULT FALSE,
    settled_at    TIMESTAMP NULL,
    FOREIGN KEY (space_id)   REFERENCES spaces(space_id) ON DELETE CASCADE,
    FOREIGN KEY (from_user)  REFERENCES users(user_id)   ON DELETE CASCADE,
    FOREIGN KEY (to_user)    REFERENCES users(user_id)   ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chat_messages (
    message_id        INT AUTO_INCREMENT PRIMARY KEY,
    space_id          INT NOT NULL,
    sender_id         INT NOT NULL,
    message           TEXT NOT NULL,
    file_url          VARCHAR(512) DEFAULT NULL,
    file_type         VARCHAR(50) DEFAULT NULL,
    original_filename VARCHAR(255) DEFAULT NULL,
    is_pinned         TINYINT(1) DEFAULT 0,
    is_read           BOOLEAN DEFAULT FALSE,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (space_id)  REFERENCES spaces(space_id) ON DELETE CASCADE,
    FOREIGN KEY (sender_id) REFERENCES users(user_id)   ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS private_conversations (
    conversation_id INT AUTO_INCREMENT PRIMARY KEY,
    space_id        INT NOT NULL,
    user_low        INT NOT NULL,
    user_high       INT NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (space_id)  REFERENCES spaces(space_id) ON DELETE CASCADE,
    FOREIGN KEY (user_low)  REFERENCES users(user_id)   ON DELETE CASCADE,
    FOREIGN KEY (user_high) REFERENCES users(user_id)   ON DELETE CASCADE,
    CONSTRAINT unique_conv UNIQUE (space_id, user_low, user_high)
);

CREATE TABLE IF NOT EXISTS private_messages (
    message_id      INT AUTO_INCREMENT PRIMARY KEY,
    conversation_id INT NOT NULL,
    sender_id       INT NOT NULL,
    message         TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES private_conversations(conversation_id) ON DELETE CASCADE,
    FOREIGN KEY (sender_id)       REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS media (
    media_id            INT AUTO_INCREMENT PRIMARY KEY,
    space_id            INT NOT NULL,
    uploaded_by         INT NOT NULL,
    file_path           VARCHAR(500) NOT NULL,
    cloudinary_public_id VARCHAR(255) NULL,
    file_type           VARCHAR(50)  NOT NULL,
    file_size           INT NOT NULL CHECK (file_size <= 1048576),
    visibility          ENUM('ALL','SELECTED') DEFAULT 'ALL',
    seen                BOOLEAN DEFAULT FALSE,
    uploaded_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (space_id)    REFERENCES spaces(space_id) ON DELETE CASCADE,
    FOREIGN KEY (uploaded_by) REFERENCES users(user_id)   ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS media_access (
    media_id INT NOT NULL,
    user_id  INT NOT NULL,
    PRIMARY KEY (media_id, user_id),
    FOREIGN KEY (media_id) REFERENCES media(media_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id)  REFERENCES users(user_id)  ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS events (
    event_id    INT AUTO_INCREMENT PRIMARY KEY,
    space_id    INT NOT NULL,
    title       VARCHAR(100) NOT NULL,
    description TEXT,
    location    VARCHAR(100),
    event_date  DATE NOT NULL,
    start_time  TIME,
    end_time    TIME,
    created_by  INT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (space_id)   REFERENCES spaces(space_id) ON DELETE CASCADE,
    FOREIGN KEY (created_by) REFERENCES users(user_id)   ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS event_attendance (
    event_id INT NOT NULL,
    user_id  INT NOT NULL,
    status   ENUM('GOING','MAYBE','NOT_GOING') DEFAULT 'GOING',
    PRIMARY KEY (event_id, user_id),
    FOREIGN KEY (event_id) REFERENCES events(event_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id)  REFERENCES users(user_id)   ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS resources (
    resource_id   INT AUTO_INCREMENT PRIMARY KEY,
    space_id      INT NOT NULL,
    uploaded_by   INT NOT NULL,
    title         VARCHAR(100) NOT NULL,
    resource_type ENUM('FILE','LINK') NOT NULL,
    path_or_url   TEXT NOT NULL,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (space_id)    REFERENCES spaces(space_id) ON DELETE CASCADE,
    FOREIGN KEY (uploaded_by) REFERENCES users(user_id)   ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notes (
    note_id           INT AUTO_INCREMENT PRIMARY KEY,
    space_id          INT NOT NULL,
    created_by        INT NOT NULL,
    title             VARCHAR(100) NOT NULL,
    content           TEXT,
    source_message_id INT DEFAULT NULL,
    seen              BOOLEAN DEFAULT FALSE,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (space_id)          REFERENCES spaces(space_id)        ON DELETE CASCADE,
    FOREIGN KEY (created_by)        REFERENCES users(user_id)          ON DELETE CASCADE,
    FOREIGN KEY (source_message_id) REFERENCES chat_messages(message_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    notification_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id         INT NOT NULL,
    message         VARCHAR(255) NOT NULL,
    is_read         BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS query_log (
    log_id        INT AUTO_INCREMENT PRIMARY KEY,
    user_id       INT NULL,
    action_label  VARCHAR(100),
    query_type    VARCHAR(10),
    sql_text      TEXT NOT NULL,
    params_json   TEXT,
    status        VARCHAR(20) NOT NULL,
    error_message TEXT,
    rows_affected INT DEFAULT 0,
    duration_ms   DECIMAL(8,2),
    route         VARCHAR(100),
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_created (created_at),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
);
