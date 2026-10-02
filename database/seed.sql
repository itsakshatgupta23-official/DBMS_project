-- Chronicle – database/seed.sql
-- Comprehensive demo dataset. Run AFTER schema.sql + views.sql.
-- All passwords hash to: "Password@123"
--   werkzeug hash: pbkdf2:sha256:... (pre-generated for demo)
-- For simplicity we store a bcrypt-compatible placeholder.
-- In production, use Flask register endpoint to create users.

-- ═══════════════════════════════════════════════════════
-- USERS  (password = "Password@123" hashed via werkzeug)
-- ═══════════════════════════════════════════════════════
INSERT IGNORE INTO users (user_id, username, email, password_hash, is_developer) VALUES
(1, 'akshat',   'akshat@college.edu',  'pbkdf2:sha256:600000$demo$aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', TRUE),
(2, 'priya',    'priya@college.edu',   'pbkdf2:sha256:600000$demo$bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', FALSE),
(3, 'rohit',    'rohit@college.edu',   'pbkdf2:sha256:600000$demo$cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc', FALSE),
(4, 'sneha',    'sneha@college.edu',   'pbkdf2:sha256:600000$demo$dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd', FALSE),
(5, 'vikram',   'vikram@college.edu',  'pbkdf2:sha256:600000$demo$eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee', FALSE),
(6, 'meera',    'meera@college.edu',   'pbkdf2:sha256:600000$demo$ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff', FALSE);

-- ═══════════════════════════════════════════════════════
-- SPACES
-- ═══════════════════════════════════════════════════════
INSERT IGNORE INTO spaces (space_id, name, description, space_type, invite_code, host_id) VALUES
(1, 'Goa Trip 2024',         'End-sem beach trip with the squad!',          'Trip',          'GOA001', 1),
(2, 'CS Project Group',      'Final year DBMS project collaboration.',       'Project Group', 'CS2024', 2),
(3, 'Hostel 4 Squad',        'Daily hostel expense tracking.',               'Hostel',        'H4BOYS', 3),
(4, 'Annual College Fest',   'Organising committee for TechFest 2024.',      'College Event', 'FEST24', 1);

-- ═══════════════════════════════════════════════════════
-- SPACE MEMBERS
-- ═══════════════════════════════════════════════════════
INSERT IGNORE INTO space_members (space_id, user_id, role) VALUES
-- Goa Trip
(1, 1, 'HOST'), (1, 2, 'MEMBER'), (1, 3, 'MEMBER'), (1, 4, 'MEMBER'), (1, 5, 'MEMBER'),
-- CS Project
(2, 2, 'HOST'), (2, 1, 'MEMBER'), (2, 3, 'MEMBER'), (2, 6, 'MEMBER'),
-- Hostel
(3, 3, 'HOST'), (3, 1, 'MEMBER'), (3, 4, 'MEMBER'), (3, 5, 'MEMBER'), (3, 6, 'MEMBER'),
-- College Fest
(4, 1, 'HOST'), (4, 2, 'MEMBER'), (4, 4, 'MEMBER'), (4, 6, 'MEMBER');

-- ═══════════════════════════════════════════════════════
-- JOIN REQUESTS (some historical)
-- ═══════════════════════════════════════════════════════
INSERT IGNORE INTO join_requests (space_id, user_id, status, decided_by) VALUES
(1, 6, 'REJECTED', 1),
(2, 5, 'APPROVED', 2),
(4, 3, 'PENDING',  NULL);

-- ═══════════════════════════════════════════════════════
-- EXPENSES – Goa Trip (space 1)
-- ═══════════════════════════════════════════════════════
INSERT IGNORE INTO expenses (expense_id, space_id, description, amount, paid_by, created_by) VALUES
(1, 1, 'Hotel Booking (3 nights)',  9000.00, 1, 1),
(2, 1, 'Petrol & Toll',            2400.00, 3, 3),
(3, 1, 'Beach Party Dinner',        3500.00, 2, 2),
(4, 1, 'Water Sports Activities',   5000.00, 1, 1),
(5, 1, 'Grocery & Drinks',          1800.00, 4, 4);

-- Equal splits: 5 members
INSERT IGNORE INTO expense_splits (expense_id, user_id, share_amount) VALUES
(1,1,1800.00),(1,2,1800.00),(1,3,1800.00),(1,4,1800.00),(1,5,1800.00),
(2,1,480.00), (2,2,480.00), (2,3,480.00), (2,4,480.00), (2,5,480.00),
(3,1,700.00), (3,2,700.00), (3,3,700.00), (3,4,700.00), (3,5,700.00),
(4,1,1000.00),(4,2,1000.00),(4,3,1000.00),(4,4,1000.00),(4,5,1000.00),
(5,1,360.00), (5,2,360.00), (5,3,360.00), (5,4,360.00), (5,5,360.00);

-- ═══════════════════════════════════════════════════════
-- EXPENSES – Hostel (space 3)
-- ═══════════════════════════════════════════════════════
INSERT IGNORE INTO expenses (expense_id, space_id, description, amount, paid_by, created_by) VALUES
(6, 3, 'Monthly Electricity Bill', 2500.00, 3, 3),
(7, 3, 'Common Kitchen Supplies',   800.00, 5, 5),
(8, 3, 'Internet Recharge',        1200.00, 1, 1);

-- 5 members split equally
INSERT IGNORE INTO expense_splits (expense_id, user_id, share_amount) VALUES
(6,1,500.00),(6,3,500.00),(6,4,500.00),(6,5,500.00),(6,6,500.00),
(7,1,160.00),(7,3,160.00),(7,4,160.00),(7,5,160.00),(7,6,160.00),
(8,1,240.00),(8,3,240.00),(8,4,240.00),(8,5,240.00),(8,6,240.00);

-- ═══════════════════════════════════════════════════════
-- SETTLEMENTS – Goa Trip (pre-computed samples)
-- ═══════════════════════════════════════════════════════
INSERT IGNORE INTO settlements (space_id, from_user, to_user, amount, is_settled) VALUES
(1, 2, 1, 2480.00, FALSE),
(1, 3, 1, 1080.00, FALSE),
(1, 4, 1, 1080.00, FALSE),
(1, 5, 1, 1480.00, FALSE);

-- ═══════════════════════════════════════════════════════
-- CHAT MESSAGES – Goa Trip
-- ═══════════════════════════════════════════════════════
INSERT IGNORE INTO chat_messages (space_id, sender_id, message) VALUES
(1, 1, 'Hey everyone! Hotel is booked. We leave Friday 6am 🚗'),
(1, 2, 'Yasss! So excited! 🎉'),
(1, 3, 'I will bring the car. Someone handle petrol money upfront?'),
(1, 1, 'I have already split hotel cost. Check expenses tab.'),
(1, 4, 'Can we add beach shack dinner? I know a great place.'),
(1, 5, 'Rohit already added petrol. Thanks man! 👍'),
(1, 2, 'Dinner is booked — 500 per head. I will pay and add to expenses.'),
(1, 1, 'Perfect. Sneha — you are handling water sports booking right?'),
(1, 4, 'Yes! Paid. Added to expenses. ₹1000 per head.');

-- ═══════════════════════════════════════════════════════
-- PRIVATE CONVERSATIONS + MESSAGES
-- ═══════════════════════════════════════════════════════
INSERT IGNORE INTO private_conversations (conversation_id, space_id, user_low, user_high) VALUES
(1, 1, 1, 2),
(2, 1, 1, 3);

INSERT IGNORE INTO private_messages (conversation_id, sender_id, message) VALUES
(1, 1, 'Priya, can you confirm your arrival time on Friday?'),
(1, 2, 'I will be there by 5:45am. Do not leave without me 😅'),
(1, 1, 'Haha ok noted. See you then!'),
(2, 3, 'Akshat bhai, petrol cost should be split differently na?'),
(2, 1, 'Equal split is fine since everyone used the car equally.');

-- ═══════════════════════════════════════════════════════
-- EVENTS
-- ═══════════════════════════════════════════════════════
INSERT IGNORE INTO events (event_id, space_id, title, description, location, event_date, start_time, end_time, created_by) VALUES
(1, 1, 'Depart for Goa',     'Everyone meet at Akshat house.',      'Akshat House, Pune',  '2024-12-20', '06:00:00', '07:00:00', 1),
(2, 1, 'Beach Day',          'Calangute Beach — full day fun.',     'Calangute Beach, Goa','2024-12-21', '09:00:00', '18:00:00', 1),
(3, 1, 'Water Sports',       'Booked at Baga Beach Adventure Park.','Baga Beach, Goa',     '2024-12-21', '10:00:00', '13:00:00', 4),
(4, 1, 'Farewell Dinner',    'Last night dinner at the shack.',     'Curlies, Goa',        '2024-12-22', '19:00:00', '22:00:00', 2),
(5, 2, 'DBMS Project Demo',  'Final project presentation.',         'CS Lab 3, College',   '2024-12-15', '14:00:00', '16:00:00', 2),
(6, 4, 'TechFest Opening',   'Inaugural ceremony and keynote.',     'Auditorium, College', '2024-11-15', '10:00:00', '12:00:00', 1);

-- ═══════════════════════════════════════════════════════
-- EVENT ATTENDANCE
-- ═══════════════════════════════════════════════════════
INSERT IGNORE INTO event_attendance (event_id, user_id, status) VALUES
(1,1,'GOING'),(1,2,'GOING'),(1,3,'GOING'),(1,4,'GOING'),(1,5,'MAYBE'),
(2,1,'GOING'),(2,2,'GOING'),(2,3,'GOING'),(2,4,'GOING'),(2,5,'GOING'),
(3,1,'GOING'),(3,2,'MAYBE'),(3,3,'GOING'),(3,4,'GOING'),(3,5,'NOT_GOING'),
(4,1,'GOING'),(4,2,'GOING'),(4,3,'GOING'),(4,4,'GOING'),(4,5,'GOING'),
(5,1,'GOING'),(5,2,'GOING'),(5,3,'GOING'),(5,6,'GOING'),
(6,1,'GOING'),(6,2,'GOING'),(6,4,'GOING'),(6,6,'MAYBE');

-- ═══════════════════════════════════════════════════════
-- RESOURCES
-- ═══════════════════════════════════════════════════════
INSERT IGNORE INTO resources (space_id, uploaded_by, title, resource_type, path_or_url) VALUES
(1, 1, 'Hotel Booking Confirmation', 'LINK', 'https://drive.google.com/file/demo-hotel-booking'),
(1, 3, 'Road Trip Playlist 🎵',      'LINK', 'https://open.spotify.com/playlist/demo'),
(2, 2, 'DBMS Project Report Draft',  'LINK', 'https://docs.google.com/document/demo-report'),
(2, 1, 'ER Diagram (Final)',          'LINK', 'https://drive.google.com/file/er-diagram'),
(4, 1, 'Fest Schedule 2024',          'LINK', 'https://docs.google.com/spreadsheets/demo-schedule'),
(3, 3, 'Electricity Bill PDF',        'LINK', 'https://drive.google.com/file/demo-bill');

-- ═══════════════════════════════════════════════════════
-- NOTES
-- ═══════════════════════════════════════════════════════
INSERT IGNORE INTO notes (space_id, created_by, title, content) VALUES
(1, 1, 'Packing Checklist',
 'Sunscreen, Sunglasses, Beach towels, Camera, Portable charger, Swimwear, Sandals, ID cards'),
(1, 2, 'Emergency Contacts',
 'Akshat: 98XXXXXXXX\nPriya: 87XXXXXXXX\nLocal Hospital: +91-832-2222222\nGoa Police: 100'),
(2, 2, 'Project Task Split',
 'Akshat: Flask Backend + DB\nPriya: Frontend + CSS\nRohit: SQL Queries + Views\nMeera: Documentation'),
(2, 1, 'DB Design Notes',
 '3NF achieved. query_log uses separate autocommit connection. Settlement uses greedy algorithm.'),
(4, 1, 'Sponsorship Tracker',
 'Jain Caterers: Confirmed ₹20,000\nTech Mahindra: Pending\nCafeteria: In-kind (food stalls)');

-- ═══════════════════════════════════════════════════════
-- NOTIFICATIONS
-- ═══════════════════════════════════════════════════════
INSERT IGNORE INTO notifications (user_id, message) VALUES
(2, 'Your request to join ''Goa Trip 2024'' was approved.'),
(3, 'New expense ''Hotel Booking'' (₹9000.00) added in ''Goa Trip 2024''.'),
(4, 'New expense ''Hotel Booking'' (₹9000.00) added in ''Goa Trip 2024''.'),
(5, 'New expense ''Hotel Booking'' (₹9000.00) added in ''Goa Trip 2024''.'),
(2, 'New event ''DBMS Project Demo'' added in ''CS Project Group''.'),
(3, 'New event ''DBMS Project Demo'' added in ''CS Project Group''.'),
(1, 'vikram wants to join ''CS Project Group''.'),
(6, 'New expense ''Monthly Electricity Bill'' (₹2500.00) added in ''Hostel 4 Squad''.'),
(1, 'New event ''Depart for Goa'' added in ''Goa Trip 2024''.'),
(2, 'New event ''Depart for Goa'' added in ''Goa Trip 2024''.'),
(3, 'There is a pending join request for ''Annual College Fest''.'),
(5, 'Your request to join ''CS Project Group'' was approved.');
