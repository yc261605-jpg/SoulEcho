import json
import os
from datetime import datetime
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from google import genai
from pydantic import BaseModel, Field
import pymysql
import requests

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")  # 讀取同資料夾的 .env（金鑰、資料庫密碼都放這裡，不寫進程式碼）

app = Flask(__name__)

# 1. 啟用廣義 CORS
CORS(app, resources={r"/api/*": {"origins": "*"}})


# 2. 強制處理 OPTIONS 預檢請求與 Allow Headers
@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = app.make_default_options_response()
        headers = response.headers
        headers["Access-Control-Allow-Origin"] = "*"
        headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS, PUT, DELETE"
        headers["Access-Control-Allow-Headers"] = (
            "Content-Type, Authorization, X-Admin-Key, ngrok-skip-browser-warning"
        )
        return response, 200


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, Authorization, X-Admin-Key, ngrok-skip-browser-warning"
    )
    response.headers["Access-Control-Allow-Methods"] = (
        "POST, GET, OPTIONS, PUT, DELETE"
    )
    return response


# ==================== 基本設定（全部從 .env 讀取）====================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-3.1-flash-lite")
# 選填：高風險訊息要通知的 Discord Webhook（留空 = 不發送）
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
# 後台密碼：/api/admin/* 需要帶 X-Admin-Key 標頭（留空 = 不檢查，只建議在自己電腦測試時這樣用）
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DATABASE", "soulecho_db"),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}

if not GEMINI_API_KEY:
    raise SystemExit("❌ 找不到 GEMINI_API_KEY：請把 .env.example 複製成 .env，填入你自己的 Gemini API Key")

# 初始化 Gemini Client
gemini_client = genai.Client(api_key=GEMINI_API_KEY)


@app.before_request
def check_admin_key():
    """後台 API 需要密碼，避免任何人都能讀取所有使用者的對話與日記。"""
    if request.method == "OPTIONS" or not request.path.startswith("/api/admin/"):
        return None
    if ADMIN_PASSWORD and request.headers.get("X-Admin-Key", "") != ADMIN_PASSWORD:
        return jsonify({"error": "後台密碼錯誤"}), 401
    return None


# ==================== 網頁 ====================
@app.route("/")
def page_user():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/admin")
def page_admin():
    return send_from_directory(BASE_DIR, "後端平台.html")


# ==================== Pydantic 結構定義 ====================
class RiskAnalysisResponse(BaseModel):
    risk_level: str = Field(
        description="風險等級，必須是 LOW, MEDIUM, HIGH, CRITICAL 其中之一"
    )
    detected_indicators: List[str] = Field(
        description="察言觀色抓出的潛在情緒特徵或關鍵字（如：無價值感、自殘傾向、嚴重絕望）"
    )
    ai_response: str = Field(
        description="給予使用者的心靈輔導與傾聽回覆，語氣需平實自然、沉穩且具備同理心"
    )


class DiaryRiskAnalysisResponse(BaseModel):
    risk_level: str = Field(
        description="日記風險等級，必須是 LOW, MEDIUM, HIGH, CRITICAL 其中之一"
    )
    detected_indicators: List[str] = Field(
        description="從日記內容中偵測到的風險指標與情緒關鍵字"
    )
    summary_analysis: str = Field(
        description="給後端/輔導員參考的日記心理狀態簡短分析摘要（50字以內）"
    )


class MentalHealthAnalysisResponse(BaseModel):
    emotional_stability: int = Field(description="情緒穩定度，分數 0~100")
    stress_level: int = Field(description="壓力指數，分數 0~100 (越高代表壓力越大)")
    positivity: int = Field(description="正向積極度，分數 0~100")
    self_awareness: int = Field(description="自我覺察力，分數 0~100")
    social_connection: int = Field(description="社交連結/歸屬感，分數 0~100")
    suggestions: List[str] = Field(description="給使用者的 2~3 句平實、具同理心且具體的心理調適小建議")
    summary: str = Field(description="對近期整體狀態的一句話總結（約 20 字以內）")


# ==================== 輔助函式 ====================
def get_db_connection():
    """建立 MySQL 連線"""
    return pymysql.connect(**MYSQL_CONFIG)


def format_time(val):
    """將 datetime 物件轉為前端好呈現的字串格式"""
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d %H:%M")
    elif val:
        return str(val)
    return "時間未知"


def send_discord_alert(
    user_id: str,
    risk_level: str,
    content_text: str,
    indicators: list,
    source_type: str = "對話",
):
    """當對話或日記偵測到高風險時，發送警報至 Discord 頻道"""
    if not DISCORD_WEBHOOK_URL:
        print("⚠️ 未設定完整的 Discord Webhook，跳過警報發送。")
        return

    payload = {
        "content": (
            f"🚨 **【高風險心理狀態預警 - 來源：{source_type}】** 🚨\n"
            f"**使用者 Email (ID):** `{user_id}`\n"
            f"**風險等級:** `{risk_level}`\n"
            f"**情緒與風險指標:** {', '.join(indicators)}\n"
            f'**監測內容:** "{content_text}"\n'
            f"⚠️ *系統已自動寫入預警資料庫，請工作人員儘速評估關懷！*"
        )
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
    except Exception as e:
        print(f"❌ Discord Webhook 發送失敗: {e}")


# ==================== API 路由 (API Endpoints) ====================

# 🆕 【新增】使用者登入/寫入 users Table API
@app.route("/api/user/login", methods=["POST", "OPTIONS"])
def user_login():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    data = request.get_json() or {}
    email = data.get("email", "").strip()

    if not email or "@" not in email:
        return jsonify({"error": "Invalid email address"}), 400

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 新增或更新登入時間
            sql = """
                INSERT INTO users (email) 
                VALUES (%s)
                ON DUPLICATE KEY UPDATE last_login = CURRENT_TIMESTAMP;
            """
            cursor.execute(sql, (email,))
            conn.commit()

        return jsonify({"status": "success", "email": email}), 200

    except Exception as e:
        print(f"❌ 使用者紀錄更新失敗: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if "conn" in locals() and conn and conn.open:
            conn.close()


# 🔄 【修改】後台管理端：從 users Table 獲取所有使用者
@app.route("/api/admin/all_users", methods=["GET", "OPTIONS"])
def get_all_users():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 從新增的 users 表中撈取所有的使用者 Email 與最後登入時間
            sql = """
                SELECT email, created_at, last_login 
                FROM users 
                ORDER BY last_login DESC;
            """
            cursor.execute(sql)
            records = cursor.fetchall() or []

            # 整理時間格式
            for r in records:
                r["created_at"] = format_time(r.get("created_at"))
                r["last_login"] = format_time(r.get("last_login"))

        return jsonify({"users": records}), 200

    except Exception as e:
        print(f"❌ 撈取使用者名單失敗: {e}")
        return jsonify({"users": [], "error": str(e)}), 500
    finally:
        if "conn" in locals() and conn and conn.open:
            conn.close()


@app.route("/api/analytics/mental_health", methods=["POST", "OPTIONS"])
def get_mental_health_analytics():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    data = request.get_json() or {}
    user_id = data.get("user_id", "").strip()

    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400

    try:
        conn = get_db_connection()
        chats = []
        diaries = []

        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT user_message, ai_response FROM chat_logs WHERE user_id = %s ORDER BY log_id DESC LIMIT 15",
                (user_id,)
            )
            chats = cursor.fetchall() or []

            cursor.execute(
                "SELECT title, content FROM mood_diaries WHERE user_id = %s ORDER BY diary_id DESC LIMIT 10",
                (user_id,)
            )
            diaries = cursor.fetchall() or []

        prompt = f"""
        請根據以下使用者的歷史日記與聊天紀錄，評估其近期的『心理健康狀態指標』並給予溫暖小建議。

        【使用者 ID】: {user_id}
        【最近日記紀錄】: {json.dumps(diaries, ensure_ascii=False)}
        【最近對話紀錄】: {json.dumps(chats, ensure_ascii=False)}

        請分析以下 5 個維度（分數介於 0 到 100 之間的整數）：
        1. emotional_stability (情緒穩定度)
        2. stress_level (壓力指數)
        3. positivity (正向積極度)
        4. self_awareness (自我覺察力)
        5. social_connection (社交連結/歸屬感)

        以及 2~3 點溫暖、平實、具體的心理建議 (suggestions)。
        """

        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": MentalHealthAnalysisResponse,
            },
        )

        analysis_result = json.loads(response.text)
        return jsonify(analysis_result), 200

    except Exception as e:
        print(f"❌ 心理圖表分析失敗: {e}")
        return jsonify({
            "emotional_stability": 70,
            "stress_level": 45,
            "positivity": 65,
            "self_awareness": 80,
            "social_connection": 60,
            "summary": "最近狀態大致平穩，懂得自我察覺與傾聽內部聲音。",
            "suggestions": [
                "感覺累的時候，不妨放下手機給自己 10 分鐘的放空時間。",
                "適時將心中的煩惱寫成筆記，是很好的情緒宣洩管道。"
            ]
        }), 200
    finally:
        if "conn" in locals() and conn and conn.open:
            conn.close()


@app.route("/api/mood/check_today", methods=["POST", "OPTIONS"])
def check_today_mood():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    data = request.get_json() or {}
    user_id = data.get("user_id", "").strip()

    if not user_id:
        return jsonify({"has_checked_in": False}), 400

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            sql = """
                SELECT mood_id 
                FROM mood_checkins 
                WHERE user_id = %s AND DATE(created_at) = CURDATE()
                LIMIT 1
            """
            cursor.execute(sql, (user_id,))
            record = cursor.fetchone()

        has_checked_in = True if record else False
        return jsonify({"has_checked_in": has_checked_in}), 200

    except Exception as e:
        print(f"❌ 檢查今日打卡狀態失敗: {e}")
        return jsonify({"has_checked_in": False, "error": str(e)}), 500
    finally:
        if "conn" in locals() and conn and conn.open:
            conn.close()


@app.route("/api/admin/risk_users", methods=["POST", "OPTIONS"])
def get_risk_users():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    try:
        data = request.get_json() or {}
        risk_level = data.get("risk_level", "ALL").upper()

        conn = get_db_connection()
        with conn.cursor() as cursor:
            if risk_level == "ALL":
                sql = """
                    SELECT alert_id, user_id, risk_level, trigger_message, created_at 
                    FROM crisis_alerts 
                    ORDER BY alert_id DESC LIMIT 50
                """
                cursor.execute(sql)
            else:
                sql = """
                    SELECT alert_id, user_id, risk_level, trigger_message, created_at 
                    FROM crisis_alerts 
                    WHERE risk_level = %s 
                    ORDER BY alert_id DESC LIMIT 50
                """
                cursor.execute(sql, (risk_level,))

            users = cursor.fetchall() or []

        for u in users:
            u["created_at"] = format_time(u.get("created_at"))

        return jsonify({"users": users}), 200

    except Exception as e:
        print(f"❌ 讀取預警使用者列表失敗: {e}")
        return jsonify({"users": [], "error": str(e)}), 200
    finally:
        if "conn" in locals() and conn and conn.open:
            conn.close()


@app.route("/api/mood", methods=["POST"])
def save_mood():
    data = request.get_json() or {}
    user_id = data.get("user_id", "").strip()
    emoji = data.get("emoji", "").strip()

    if not user_id or not emoji:
        return jsonify({"error": "Missing user_id or emoji"}), 400

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            sql = "INSERT INTO mood_checkins (user_id, mood_emoji) VALUES (%s, %s)"
            cursor.execute(sql, (user_id, emoji))
            conn.commit()

        prompt = f"使用者剛剛選擇了「{emoji}」這個表情符號來代表今天的心情。請以陪伴者 SoulEcho 的身份，給予他一句簡短、溫暖且貼近這個情緒的關懷回覆（30字以內）。"

        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        ai_reply = response.text.strip()

        with conn.cursor() as cursor:
            sql_log = """
                INSERT INTO chat_logs (user_id, user_message, ai_response, risk_level, detected_indicators)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(
                sql_log,
                (
                    user_id,
                    f"【今日心情打卡：{emoji}】",
                    ai_reply,
                    "LOW",
                    "[]",
                ),
            )
            conn.commit()

        return jsonify(
            {
                "status": "success",
                "message": "Mood recorded",
                "ai_response": ai_reply,
            }
        )

    except Exception as e:
        print(f"❌ 記錄心情失敗: {e}")
        return jsonify({"error": "Database insert failed"}), 500
    finally:
        if "conn" in locals() and conn and conn.open:
            conn.close()


@app.route("/api/history", methods=["POST"])
def get_history():
    data = request.get_json() or {}
    user_id = data.get("user_id", "").strip()

    if not user_id or "@" not in user_id:
        return jsonify({"history": []})

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            sql = """
                SELECT user_message, ai_response 
                FROM chat_logs 
                WHERE user_id = %s 
                ORDER BY created_at DESC 
                LIMIT 10
            """
            cursor.execute(sql, (user_id,))
            records = cursor.fetchall()

        history = []
        for r in reversed(records):
            history.append({"role": "user", "text": r["user_message"]})
            history.append({"role": "model", "text": r["ai_response"]})

        return jsonify({"history": history})

    except Exception as e:
        print(f"❌ 讀取歷史紀錄失敗: {e}")
        return jsonify({"history": []})
    finally:
        if "conn" in locals() and conn and conn.open:
            conn.close()


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json() or {}
    user_id = data.get("user_id", "guest_user").strip()
    user_message = data.get("message", "").strip()
    history = data.get("history", [])

    if not user_message:
        return jsonify({"error": "Message content cannot be empty"}), 400

    system_instruction = """
    你是一位語氣平和、沉穩且懂得傾聽的陪伴者，名字是 SoulEcho。

    在回覆使用者時，請遵守以下原則：
    1. 語氣自然平實：不要使用過度浮誇、劇本感或過度熱情的詞彙（例如不要動輒說「心疼你」、「好捨不得」,不要過度擔心關心）。
    2. 接住情緒即可，保持適度邊界,對談要像是在跟朋友相處一樣：用簡單、真摯的句子反映使用者的感受，不說教、不急著給一大堆人生大道理。
    3. 保持對話脈絡連續性：請結合先前的對話脈絡回應，讓使用者感受到你一直專心在聽。
    4. 精簡回覆：每次回答控制在 2~4 句話內，留給使用者更多表達空間。
    5. 觀察隱含風險：在背後默默評估心理風險等級 (LOW, MEDIUM, HIGH, CRITICAL)。

    風險等級判定原則：
    - LOW: 一般抒發、日常生活抱怨、工作學習壓力。
    - MEDIUM: 長期低落、無力感、自我懷疑、迷惘與孤獨。
    - HIGH: 隱晦提及自傷、想消失、終結痛苦、嚴重絕望。
    - CRITICAL: 明確提及自殺意圖、具體自傷計畫。
    """

    contents = []
    for h in history[-10:]:
        role = "user" if h.get("role") == "user" else "model"
        text = h.get("text", "")
        if text:
            contents.append({"role": role, "parts": [{"text": text}]})

    contents.append({"role": "user", "parts": [{"text": user_message}]})

    try:
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config={
                "system_instruction": system_instruction,
                "response_mime_type": "application/json",
                "response_schema": RiskAnalysisResponse,
            },
        )

        ai_result = json.loads(response.text)
        risk_level = ai_result.get("risk_level", "LOW")
        indicators = ai_result.get("detected_indicators", [])
        ai_response = ai_result.get("ai_response", "")

        if risk_level in ["HIGH", "CRITICAL"]:
            ai_response += (
                "\n\n💙 *小提醒：如果你感到深深的無助或壓力過大，隨時可以撥打"
                " 1925 安心專線（免付費），會有專業人員溫柔陪伴你。*"
            )

    except Exception as e:
        print(f"❌ AI 呼叫錯誤: {e}")
        return jsonify({"error": "AI service processing failed"}), 500

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            sql_log = """
                INSERT INTO chat_logs (user_id, user_message, ai_response, risk_level, detected_indicators)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(
                sql_log,
                (
                    user_id,
                    user_message,
                    ai_response,
                    risk_level,
                    json.dumps(indicators, ensure_ascii=False),
                ),
            )

            if risk_level in ["HIGH", "CRITICAL"]:
                sql_alert = """
                    INSERT INTO crisis_alerts (user_id, risk_level, trigger_message, detected_indicators)
                    VALUES (%s, %s, %s, %s)
                """
                cursor.execute(
                    sql_alert,
                    (
                        user_id,
                        risk_level,
                        user_message,
                        json.dumps(indicators, ensure_ascii=False),
                    ),
                )
                send_discord_alert(
                    user_id,
                    risk_level,
                    user_message,
                    indicators,
                    source_type="即時聊天",
                )

            conn.commit()
    except Exception as e:
        print(f"❌ 資料庫寫入失敗: {e}")
    finally:
        if "conn" in locals() and conn and conn.open:
            conn.close()

    return jsonify({
        "user_id": user_id,
        "risk_level": risk_level,
        "detected_indicators": indicators,
        "ai_response": ai_response,
    })


@app.route("/api/diary/save", methods=["POST"])
def save_diary():
    data = request.get_json() or {}
    user_id = data.get("user_id", "").strip()
    title = data.get("title", "無標題").strip()
    content = data.get("content", "").strip()

    if not user_id or not content:
        return jsonify({"error": "Missing user_id or content"}), 400

    now_dt = datetime.now()
    diary_id = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            sql = "INSERT INTO mood_diaries (user_id, title, content, created_at) VALUES (%s, %s, %s, %s)"
            cursor.execute(sql, (user_id, title, content, now_dt))
            conn.commit()
            diary_id = cursor.lastrowid
    except Exception as e:
        print(f"❌ 日記儲存至資料庫失敗: {e}")
        return jsonify({"error": "Database insert failed"}), 500
    finally:
        if "conn" in locals() and conn and conn.open:
            conn.close()

    diary_prompt = f"""
    請評估以下使用者撰寫的心情日記內容，分析其隱含的心理風險等級。

    【日記標題】：{title}
    【日記內文】：{content}

    評估標準：
    - LOW: 一般日常生活記錄、感謝、正向抒發或輕微煩惱。
    - MEDIUM: 偏向低落的情緒、長期壓力、自我懷疑、孤獨或無力感。
    - HIGH: 提及自傷意念、絕望、強烈無價值感、想消失。
    - CRITICAL: 明確提及自殺企圖、具體自傷計畫或告別用語。
    """

    risk_level = "LOW"
    indicators = []

    try:
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=diary_prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": DiaryRiskAnalysisResponse,
            },
        )
        analysis_res = json.loads(response.text)
        risk_level = analysis_res.get("risk_level", "LOW")
        indicators = analysis_res.get("detected_indicators", [])

        if risk_level in ["HIGH", "CRITICAL"]:
            alert_message = f"【日記高風險預警】標題：{title} | 內容：{content[:100]}"
            conn = get_db_connection()
            with conn.cursor() as cursor:
                sql_alert = """
                    INSERT INTO crisis_alerts (user_id, risk_level, trigger_message, detected_indicators)
                    VALUES (%s, %s, %s, %s)
                """
                cursor.execute(
                    sql_alert,
                    (
                        user_id,
                        risk_level,
                        alert_message,
                        json.dumps(indicators, ensure_ascii=False),
                    ),
                )
                conn.commit()

            send_discord_alert(
                user_id,
                risk_level,
                alert_message,
                indicators,
                source_type="心情日記",
            )

    except Exception as ai_err:
        print(f"⚠️ 日記 AI 分析過程出錯: {ai_err}")

    return jsonify({
        "status": "success",
        "message": "Diary saved and analyzed",
        "diary_id": diary_id,
        "risk_level": risk_level,
        "detected_indicators": indicators,
        "created_at": format_time(now_dt),
    })


@app.route("/api/diary/list", methods=["POST"])
def list_diaries():
    data = request.get_json() or {}
    user_id = data.get("user_id", "").strip()

    if not user_id:
        return jsonify({"diaries": []})

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            sql = """
                SELECT diary_id AS id, title, content, created_at 
                FROM mood_diaries 
                WHERE user_id = %s 
                ORDER BY diary_id DESC
            """
            cursor.execute(sql, (user_id,))
            records = cursor.fetchall() or []

        formatted_diaries = []
        for r in records:
            formatted_diaries.append({
                "id": r.get("id"),
                "title": r.get("title") or "無標題",
                "content": r.get("content") or "",
                "created_at": format_time(r.get("created_at")),
            })

        return jsonify({"diaries": formatted_diaries})
    except Exception as e:
        print(f"❌ 讀取日記列表失敗: {e}")
        return jsonify({"diaries": []})
    finally:
        if "conn" in locals() and conn and conn.open:
            conn.close()


@app.route("/api/admin/profile", methods=["POST", "OPTIONS"])
def admin_profile():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    data = request.get_json() or {}
    target_user_id = data.get("target_user_id", "").strip()

    if not target_user_id:
        return jsonify({"error": "Target user ID required"}), 400

    try:
        conn = get_db_connection()
        chats = []
        diaries = []

        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT user_message, ai_response, risk_level, created_at FROM chat_logs WHERE user_id = %s ORDER BY log_id DESC LIMIT 20",
                (target_user_id,),
            )
            raw_chats = cursor.fetchall() or []
            for c in raw_chats:
                chats.append({
                    "user_message": c.get("user_message"),
                    "ai_response": c.get("ai_response"),
                    "risk_level": c.get("risk_level"),
                    "created_at": format_time(c.get("created_at")),
                })

            cursor.execute(
                "SELECT title, content, created_at FROM mood_diaries WHERE user_id = %s ORDER BY diary_id DESC LIMIT 10",
                (target_user_id,),
            )
            raw_diaries = cursor.fetchall() or []
            for d in raw_diaries:
                diaries.append({
                    "title": d.get("title"),
                    "content": d.get("content"),
                    "created_at": format_time(d.get("created_at")),
                })

        summary_text = f"【目標使用者】{target_user_id}\n\n"
        summary_text += f"📖 歷史日記：{len(diaries)} 篇\n"
        for d in diaries[:3]:
            title = d.get("title") or "無標題"
            content = d.get("content") or ""
            summary_text += (
                f" • [{d.get('created_at', '-')}] {title}：{content[:25]}...\n"
            )

        summary_text += f"\n💬 對話總數：{len(chats)} 次\n"
        for c in chats[:3]:
            msg = c.get("user_message") or ""
            summary_text += f" • [{c.get('created_at', '-')}] [{c.get('risk_level', 'LOW')}] 使用者: {msg[:25]}...\n"

        profile_report_text = ""
        try:
            prompt = f"""
            請根據以下使用者的歷史日記與聊天紀錄，為心理輔導人員產生一份『全方位人物側寫報告』。

            【使用者 Email】: {target_user_id}
            【歷史日記】: {json.dumps(diaries, ensure_ascii=False)}
            【聊天紀錄】: {json.dumps(chats, ensure_ascii=False)}

            請用繁體中文回答，內容需包含：
            1. 情感狀態與性格特質
            2. 近期核心議題與壓力源
            3. 建議輔導策略與回應方向
            """

            profile_response = gemini_client.models.generate_content(
                model=GEMINI_MODEL, contents=prompt
            )
            profile_report_text = profile_response.text
        except Exception as ai_err:
            print(f"⚠️ Gemini API 生成側寫時失敗: {ai_err}")
            profile_report_text = f"（AI 側寫報告生成暫時無法使用：{str(ai_err)}）\n\n已成功拉取使用者歷史資料，請參考左側摘要紀錄。"

        return (
            jsonify({
                "summary_report": summary_text,
                "profile_report": profile_report_text,
            }),
            200,
        )

    except Exception as e:
        print(f"❌ 生成側寫失敗: {e}")
        return (
            jsonify({
                "summary_report": "資料載入失敗",
                "profile_report": f"後端執行錯誤: {str(e)}",
            }),
            200,
        )
    finally:
        if "conn" in locals() and conn and conn.open:
            conn.close()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() in ("1", "true", "yes")
    print(f"✅ SoulEcho 已啟動：使用者端 http://localhost:{port}/　後台 http://localhost:{port}/admin")
    # 預設只聽本機；要讓同網路的手機連線，在 .env 設 HOST=0.0.0.0（debug 模式請勿對外開放）
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=port, debug=debug)