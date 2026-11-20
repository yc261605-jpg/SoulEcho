@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist .venv (
  echo [1/3] 第一次執行：建立虛擬環境...
  python -m venv .venv || (echo 找不到 Python，請先安裝 Python 3.10 以上版本 & pause & exit /b)
)
call .venv\Scripts\activate.bat
echo [2/3] 檢查套件...
pip install -q -r requirements.txt

if not exist .env (
  copy .env.example .env >nul
  echo.
  echo 已建立 .env，請用記事本打開，填入 GEMINI_API_KEY 和 MYSQL_PASSWORD 後再執行一次 start.bat
  notepad .env
  pause
  exit /b
)

echo [3/3] 啟動 SoulEcho...
start "" cmd /c "timeout /t 3 >nul & start http://localhost:5000"
python server2.py
pause
