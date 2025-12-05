# Firebase 部署指南

本指南將幫助您將 Flask 應用程序部署到 Firebase Hosting 和 Functions。

## 前置要求

1. 安裝 Node.js 和 npm
2. 安裝 Firebase CLI：
   ```bash
   npm install -g firebase-tools
   ```
3. 登入 Firebase：
   ```bash
   firebase login
   ```

## 部署步驟

### 1. 初始化 Firebase 項目（如果尚未初始化）

```bash
firebase init
```

選擇：
- Functions: 配置 Firebase Functions
- Hosting: 配置 Firebase Hosting
- 使用現有項目：book-exchange-d4351

### 2. 設置環境變數

在 Firebase Console 中設置 Functions 的環境變數：

```bash
firebase functions:config:set \
  firebase.api_key="YOUR_API_KEY" \
  firebase.auth_domain="YOUR_AUTH_DOMAIN" \
  openai.api_key="YOUR_OPENAI_KEY" \
  recaptcha.site_key="YOUR_RECAPTCHA_SITE_KEY" \
  recaptcha.secret_key="YOUR_RECAPTCHA_SECRET_KEY" \
  flask.secret_key="YOUR_SECRET_KEY"
```

或者使用 `.env` 文件（需要額外配置）。

### 3. 重構應用程序結構

由於原始 `app.py` 文件很大，建議進行以下重構：

1. 創建 `app/` 目錄結構：
   ```
   app/
   ├── __init__.py
   ├── routes/
   │   ├── __init__.py
   │   ├── auth.py
   │   ├── books.py
   │   ├── profile.py
   │   └── ...
   ├── utils/
   │   ├── __init__.py
   │   └── helpers.py
   └── config.py
   ```

2. 將業務邏輯提取到模塊中

3. 在 `functions/main.py` 中導入這些模塊

### 4. 部署

```bash
# 部署 Functions 和 Hosting
firebase deploy

# 或分別部署
firebase deploy --only functions
firebase deploy --only hosting
```

## 注意事項

1. **文件大小限制**：Firebase Functions 有文件大小限制，確保所有依賴都在 `requirements.txt` 中

2. **環境變數**：敏感信息（如 API keys）應該通過 Firebase Functions 配置設置，而不是硬編碼

3. **靜態文件**：將靜態文件（CSS、JS、圖片）放在 `public/` 目錄中

4. **會話存儲**：Firebase Functions 是無狀態的，考慮使用 Firestore 或其他持久化存儲來管理會話

5. **超時限制**：Functions 有執行時間限制（默認 60 秒），確保長時間運行的操作使用異步處理

## 替代方案

如果 Firebase Functions 不適合您的需求，可以考慮：

1. **Google Cloud Run**：更適合長時間運行的 Flask 應用
2. **App Engine**：Google 的完全託管平台
3. **Cloud Functions（第二代）**：支持更長的執行時間

## 故障排除

- 查看 Functions 日誌：`firebase functions:log`
- 本地測試：`firebase emulators:start`
- 檢查部署狀態：Firebase Console


