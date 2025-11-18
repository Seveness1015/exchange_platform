# 手機測試 HTTPS 解決方案

## 問題：ngrok authtoken 無效

如果遇到 ngrok 認證錯誤，有以下解決方案：

---

## 方案一：重新設置 ngrok authtoken（推薦）

### 步驟：

1. **註冊/登入 ngrok**
   - 訪問：https://dashboard.ngrok.com/
   - 註冊帳號（免費）或登入

2. **獲取新的 authtoken**
   - 登入後，訪問：https://dashboard.ngrok.com/get-started/your-authtoken
   - 複製你的 authtoken

3. **設置 authtoken**
   ```bash
   ngrok config add-authtoken 你的新authtoken
   ```

4. **啟動 ngrok**
   ```bash
   ngrok http 5000
   ```

---

## 方案二：使用 localtunnel（無需註冊）

### 安裝：
```bash
npm install -g localtunnel
```

### 使用：
1. 啟動 Flask：
   ```bash
   python app.py
   ```

2. 開啟新終端，運行：
   ```bash
   lt --port 5000
   ```

3. 會顯示一個 HTTPS URL，例如：
   ```
   https://xxxx.loca.lt
   ```

4. 在手機上訪問這個 URL

**優點：**
- 無需註冊
- 免費
- 提供 HTTPS

**缺點：**
- 每次啟動 URL 會改變
- 需要安裝 Node.js

---

## 方案三：使用 Cloudflare Tunnel（免費，穩定）

### 安裝：
1. 下載：https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/
2. 或使用包管理器安裝

### 使用：
```bash
cloudflared tunnel --url http://localhost:5000
```

**優點：**
- 免費
- 穩定
- 提供 HTTPS

---

## 方案四：使用 serveo（無需安裝）

### 使用：
```bash
ssh -R 80:localhost:5000 serveo.net
```

**優點：**
- 無需安裝額外軟體
- 無需註冊
- 提供 HTTPS

**缺點：**
- 需要 SSH 客戶端
- 可能不穩定

---

## 方案五：使用手機熱點 + 本地 IP（僅限開發測試）

如果只是測試功能，可以使用：

1. **開啟手機熱點**
2. **電腦連接到手機熱點**
3. **獲取電腦 IP**：
   ```bash
   python get_ip.py
   ```
4. **在手機瀏覽器中訪問**：
   ```
   http://你的電腦IP:5000
   ```

**注意：** 這種方式可能無法使用相機功能（因為需要 HTTPS）

---

## 推薦順序

1. **首選：localtunnel** - 最簡單，無需註冊
2. **次選：重新設置 ngrok authtoken** - 如果已經有 ngrok
3. **備選：Cloudflare Tunnel** - 最穩定

---

## 快速測試腳本

創建 `start_tunnel.bat`（Windows）：

```batch
@echo off
echo 正在啟動 Flask...
start cmd /k "python app.py"
timeout /t 3
echo 正在啟動 localtunnel...
lt --port 5000
```

然後雙擊運行即可。


