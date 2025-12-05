# 代碼重構指南

為了更好地部署到 Firebase Functions，建議將 `app.py` 重構為模塊化結構。

## 建議的目錄結構

```
exchange_platform/
├── app/
│   ├── __init__.py          # Flask 應用工廠
│   ├── config.py            # 配置管理
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py          # 認證相關路由
│   │   ├── books.py         # 書籍相關路由
│   │   ├── profile.py       # 個人資料路由
│   │   ├── message.py       # 訊息路由
│   │   └── api.py           # API 路由
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── firebase.py      # Firebase 初始化
│   │   ├── helpers.py       # 輔助函數
│   │   └── ai.py            # AI 推薦相關
│   └── models/
│       └── __init__.py
├── functions/
│   └── main.py              # Firebase Functions 入口
├── templates/               # 模板文件
├── static/                  # 靜態文件
└── app.py                   # 原始文件（保留用於本地開發）
```

## 重構步驟

### 1. 創建應用工廠模式

在 `app/__init__.py` 中：

```python
from flask import Flask
from app.config import Config
from app.utils.firebase import init_firebase

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # 初始化 Firebase
    init_firebase()
    
    # 註冊藍圖
    from app.routes.auth import auth_bp
    from app.routes.books import books_bp
    from app.routes.profile import profile_bp
    from app.routes.message import message_bp
    from app.routes.api import api_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(books_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(message_bp)
    app.register_blueprint(api_bp)
    
    return app
```

### 2. 提取配置

在 `app/config.py` 中：

```python
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'supersecretkey')
    FIREBASE_API_KEY = os.getenv('FIREBASE_API_KEY')
    FIREBASE_AUTH_DOMAIN = os.getenv('FIREBASE_AUTH_DOMAIN')
    # ... 其他配置
```

### 3. 提取 Firebase 初始化

在 `app/utils/firebase.py` 中：

```python
import firebase_admin
from firebase_admin import credentials, firestore, storage
import pyrebase
import os

db = None
auth_firebase = None

def init_firebase():
    global db, auth_firebase
    
    if not firebase_admin._apps:
        # 初始化邏輯
        pass
    
    # 初始化 Pyrebase
    pass
```

### 4. 創建藍圖

將路由按功能分組到不同的藍圖中。

## 快速重構腳本

可以使用以下 Python 腳本幫助自動化部分重構工作：

```python
# refactor_helper.py
# 這是一個輔助腳本，可以幫助提取路由到藍圖
```

## 注意事項

1. 保持向後兼容：確保重構後的代碼功能與原始代碼一致
2. 測試：重構後進行全面測試
3. 逐步遷移：可以逐步遷移，不需要一次性完成


