# SoulEcho 心靈回聲

AI 心理陪伴與風險預警系統。使用者可以和 AI 聊天、每日心情打卡、寫心情日記；系統用 Gemini 分析對話與日記的情緒風險，高風險時寫入預警資料表（可選擇同步通知 Discord），讓輔導人員在後台查看並產生 AI 側寫報告。

> 這是作品集用的原型，不是醫療產品，也不能取代專業心理諮商。

## 功能

| 使用者端 `http://localhost:5000` | 後台 `http://localhost:5000/admin` |
| --- | --- |
| Email 登入 | 依風險等級（LOW～CRITICAL）列出預警紀錄 |
| AI 傾聽對話（同時評估風險等級） | 所有使用者名單 |
| 每日心情打卡 | 單一使用者的 AI 側寫分析報告 |
| 心情日記（AI 分析日記風險） | 高風險即時通知 Discord（選填） |
| 心理健康五維度雷達圖與建議 | |

技術：Python Flask、MySQL、Google Gemini API（結構化輸出 Pydantic）、HTML／CSS／JavaScript、Chart.js

## 快速開始（Windows）

需要先安裝：[Python 3.10+](https://www.python.org/downloads/)、[MySQL 8](https://dev.mysql.com/downloads/installer/)，並準備一組 [Gemini API Key](https://aistudio.google.com/apikey)（免費）。

1. **建立資料庫**：用 MySQL Workbench 開啟 `new.sql` 全部執行（或在終端機輸入 `mysql -u root -p < new.sql`）。
2. **雙擊 `start.bat`**。第一次會自動建立虛擬環境、安裝套件，並打開 `.env` 讓你填：
   - `GEMINI_API_KEY`：你的 Gemini 金鑰
   - `MYSQL_PASSWORD`：你的 MySQL root 密碼
   - `ADMIN_PASSWORD`：自訂後台密碼
3. 存檔後**再雙擊一次 `start.bat`**，瀏覽器會自動打開使用者端。後台在 `/admin`，第一次開啟會詢問後台密碼。

### macOS／Linux

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # 編輯 .env 填入金鑰與密碼
python server2.py
```

## 設定說明（`.env`）

| 變數 | 說明 |
| --- | --- |
| `GEMINI_API_KEY` | 必填。Gemini API 金鑰 |
| `GEMINI_MODEL` | 使用的 Gemini 模型 |
| `MYSQL_*` | 資料庫連線資訊 |
| `ADMIN_PASSWORD` | 後台密碼；留空則不檢查（只建議本機測試） |
| `DISCORD_WEBHOOK_URL` | 選填，高風險通知 |
| `HOST` / `PORT` | 預設只有本機能連；同 Wi-Fi 的手機要連，改 `HOST=0.0.0.0` |

`.env` 已列在 `.gitignore`，金鑰與密碼不會上傳到 GitHub。

## 檔案結構

```
server2.py      後端 API（Flask）＋送出兩個網頁
index.html      使用者端
後端平台.html    輔導人員後台
new.sql         MySQL 資料表
start.bat       Windows 一鍵啟動
.env.example    設定範本
```

## 已知限制

- 登入只用 Email、沒有密碼，任何人輸入別人的 Email 就能看到對方紀錄；正式上線需要加上真正的帳號驗證。
- 對話與日記屬於敏感個資，請只用測試資料展示。
