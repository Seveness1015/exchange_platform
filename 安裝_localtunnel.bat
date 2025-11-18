@echo off
echo ========================================
echo 安裝 localtunnel
echo ========================================
echo.
echo 正在檢查 Node.js...
where node >nul 2>&1
if errorlevel 1 (
    echo 錯誤：未找到 Node.js
    echo.
    echo 請先安裝 Node.js：
    echo 1. 訪問 https://nodejs.org/
    echo 2. 下載並安裝 LTS 版本
    echo 3. 重新運行此腳本
    echo.
    pause
    exit
)

echo Node.js 已安裝
echo.
echo 正在安裝 localtunnel...
npm install -g localtunnel

if errorlevel 1 (
    echo.
    echo 安裝失敗，請檢查網路連接或使用管理員權限運行
    pause
    exit
)

echo.
echo ========================================
echo 安裝完成！
echo ========================================
echo.
echo 使用方法：
echo 1. 啟動 Flask: python app.py
echo 2. 開啟新終端運行: lt --port 5000
echo 3. 複製顯示的 HTTPS URL 到手機瀏覽器
echo.
pause


