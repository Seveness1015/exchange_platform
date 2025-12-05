# 快速部署指南

## 前置步驟

### 1. 安裝 Firebase CLI

```bash
npm install -g firebase-tools
```

### 2. 登入 Firebase

```bash
firebase login
```

### 3. 初始化項目（如果尚未初始化）

```bash
firebase init
```

選擇：
- ✅ Functions: 配置 Firebase Functions
- ✅ Hosting: 配置 Firebase Hosting
- 使用現有項目：`book-exchange-d4351`

## 部署步驟

### 步驟 1: 設置環境變數

在 Firebase Console 中設置 Functions 環境變數，或使用 CLI：

```bash
# 設置環境變數（需要先從 .env 文件讀取值）
firebase functions:config:set \
  firebase.api_key="$(grep FIREBASE_API_KEY .env | cut -d '=' -f2)" \
  firebase.auth_domain="$(grep FIREBASE_AUTH_DOMAIN .env | cut -d '=' -f2)" \
  openai.api_key="$(grep OPENAI_API_KEY .env | cut -d '=' -f2)" \
  recaptcha.site_key="$(grep RECAPTCHA_SITE_KEY .env | cut -d '=' -f2)" \
  recaptcha.secret_key="$(grep RECAPTCHA_SECRET_KEY .env | cut -d '=' -f2)" \
  flask.secret_key="supersecretkey"
```

或者手動在 Firebase Console 中設置：
1. 前往 Firebase Console
2. 選擇項目：book-exchange-d4351
3. Functions → 配置 → 環境變數
4. 添加所需的環境變數

### 步驟 2: 修改 app.py 以讀取 Firebase 配置

在 `app.py` 開頭添加：

```python
import os

# 在 Firebase Functions 環境中，從配置讀取環境變數
if os.getenv('FIREBASE_FUNCTIONS') == '1':
    import firebase_functions_config
    firebase_api_key = firebase_functions_config.firebase().api_key
    firebase_auth_domain = firebase_functions_config.firebase().auth_domain
    openai_api_key = firebase_functions_config.openai().api_key
    # ... 其他配置
else:
    # 本地開發環境
    from dotenv import load_dotenv
    load_dotenv()
    firebase_api_key = os.getenv("FIREBASE_API_KEY")
    # ... 其他配置
```

### 步驟 3: 複製必要文件到 functions 目錄

```bash
# 複製模板和靜態文件（如果需要）
# 注意：Firebase Functions 可以訪問項目根目錄的文件
# 但為了更好的組織，可以創建符號連結或複製文件
```

### 步驟 4: 部署

```bash
# 部署所有內容
firebase deploy

# 或分別部署
firebase deploy --only functions
firebase deploy --only hosting
```

## 本地測試

在部署前，可以使用 Firebase Emulators 進行本地測試：

```bash
# 安裝 emulators
firebase init emulators

# 啟動 emulators
firebase emulators:start
```

## 重要注意事項

1. **文件大小**：確保 `functions/` 目錄不超過 Firebase Functions 的限制
2. **依賴**：所有 Python 依賴必須在 `functions/requirements.txt` 中
3. **環境變數**：敏感信息必須通過 Firebase 配置設置
4. **會話存儲**：考慮使用 Firestore 或其他持久化存儲來管理會話
5. **超時**：Functions 有執行時間限制，長時間運行的操作需要異步處理

## 故障排除

### 問題：導入錯誤

如果遇到導入錯誤，確保：
- `functions/main.py` 正確設置了 Python 路徑
- 所有依賴都在 `requirements.txt` 中
- Firebase 憑證正確配置

### 問題：環境變數未設置

檢查：
- Firebase Console 中的環境變數配置
- `functions/main.py` 中正確讀取配置

### 問題：靜態文件無法訪問

確保：
- 靜態文件在 `public/` 目錄中
- `firebase.json` 中的 hosting 配置正確

## 查看日誌

```bash
# 查看 Functions 日誌
firebase functions:log

# 查看特定函數的日誌
firebase functions:log --only app
```

## 更新部署

修改代碼後，重新部署：

```bash
firebase deploy --only functions
```


