@echo off
echo ========================================
echo 手機測試 HTTPS 隧道啟動腳本
echo ========================================
echo.
echo 請選擇使用的工具：
echo 1. localtunnel (推薦，無需註冊)
echo 2. ngrok (需要註冊)
echo 3. 僅啟動 Flask (不使用隧道)
echo.
set /p choice=請輸入選項 (1/2/3): 

if "%choice%"=="1" (
    echo.
    echo 正在檢查 localtunnel...
    where lt >nul 2>&1
    if errorlevel 1 (
        echo localtunnel 未安裝，正在安裝...
        npm install -g localtunnel
    )
    echo.
    echo 正在啟動 Flask...
    start cmd /k "python app.py"
    timeout /t 3
    echo.
    echo 正在啟動 localtunnel...
    echo 請複製顯示的 HTTPS URL 到手機瀏覽器訪問
    echo.
    lt --port 5000
) else if "%choice%"=="2" (
    echo.
    echo 正在啟動 Flask...
    start cmd /k "python app.py"
    timeout /t 3
    echo.
    echo 正在啟動 ngrok...
    echo 請複製顯示的 HTTPS URL 到手機瀏覽器訪問
    echo.
    ngrok http 5000
) else if "%choice%"=="3" (
    echo.
    echo 正在啟動 Flask...
    python app.py
) else (
    echo 無效的選項
    pause
)


