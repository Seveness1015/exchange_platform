"""
Firebase 初始化模塊
處理 Firebase Admin 和 Pyrebase 的初始化
"""
import firebase_admin
import pyrebase
from firebase_admin import credentials, firestore, storage
import os
import sys

# 全局變數
db = None
auth_firebase = None
firebase = None

def init_firebase():
    """初始化 Firebase Admin 和 Pyrebase"""
    global db, auth_firebase, firebase
    
    # 初始化 Firebase Admin
    if not firebase_admin._apps:
        # 查找 firebase_config.json 文件
        config_path = "firebase_config.json"
        
        if os.getenv('FIREBASE_FUNCTIONS') == '1':
            # 嘗試從項目根目錄查找
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            config_path = os.path.join(project_root, "firebase_config.json")
        
        if not os.path.exists(config_path):
            # 嘗試使用環境變數中的憑證
            cred_json = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
            if cred_json:
                import json
                cred = credentials.Certificate(json.loads(cred_json))
            else:
                raise FileNotFoundError(f"找不到 firebase_config.json 文件：{config_path}")
        else:
            cred = credentials.Certificate(config_path)
        
        firebase_admin.initialize_app(cred)
    
    db = firestore.client()
    
    # 初始化 Pyrebase（用於身份驗證）
    from app.config import Config
    
    firebase_api_key = Config.get_firebase_api_key()
    firebase_auth_domain = Config.get_firebase_auth_domain()
    
    if not firebase_api_key or not firebase_auth_domain:
        raise ValueError("Firebase API Key 或 Auth Domain 未設置")
    
    firebase_config_dict = {
        "apiKey": firebase_api_key,
        "authDomain": firebase_auth_domain,
        "databaseURL": Config.FIREBASE_DATABASE_URL,
        "projectId": Config.FIREBASE_PROJECT_ID,
        "storageBucket": Config.FIREBASE_STORAGE_BUCKET,
        "messagingSenderId": Config.FIREBASE_MESSAGING_SENDER_ID,
        "appId": Config.FIREBASE_APP_ID,
        "measurementId": Config.FIREBASE_MEASUREMENT_ID
    }
    
    firebase = pyrebase.initialize_app(firebase_config_dict)
    auth_firebase = firebase.auth()
    
    return db, auth_firebase

def get_db():
    """獲取 Firestore 數據庫實例"""
    global db
    if db is None:
        init_firebase()
    return db

def get_auth():
    """獲取 Firebase Auth 實例"""
    global auth_firebase
    if auth_firebase is None:
        init_firebase()
    return auth_firebase

