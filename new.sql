CREATE DATABASE IF NOT EXISTS soulecho_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE soulecho_db;

-- 1. 對話與風險紀錄表
CREATE TABLE IF NOT EXISTS chat_logs (
    log_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    user_message TEXT NOT NULL,
    ai_response TEXT NOT NULL,
    risk_level VARCHAR(20) DEFAULT 'Low',
    detected_indicators TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. 每日心情打卡紀錄表
CREATE TABLE IF NOT EXISTS mood_checkins (
    checkin_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    mood_emoji VARCHAR(10) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. 心情日記紀錄表
CREATE TABLE IF NOT EXISTS mood_diaries (
    diary_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    title VARCHAR(255) DEFAULT '無標題日記',
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS crisis_alerts (
    alert_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    risk_level VARCHAR(20) NOT NULL,
    trigger_message TEXT NOT NULL,
    detected_indicators JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- 5. 使用者名單（登入時寫入／更新最後登入時間）
CREATE TABLE IF NOT EXISTS users (
    email VARCHAR(255) PRIMARY KEY,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_login DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
