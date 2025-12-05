"""
配置管理模塊
處理應用程式的配置，包括環境變數和 Firebase Functions 配置
"""
import os
from dotenv import load_dotenv

# 嘗試導入 Firebase Functions 配置
try:
    from firebase_functions import config as firebase_config
    FIREBASE_FUNCTIONS = True
except ImportError:
    FIREBASE_FUNCTIONS = False
    firebase_config = None

# 載入本地環境變數（僅在非 Firebase Functions 環境）
if not FIREBASE_FUNCTIONS:
    load_dotenv()


class Config:
    """應用程式配置類"""
    
    # Flask 配置
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'supersecretkey')
    
    # Firebase 配置
    @staticmethod
    def get_firebase_api_key():
        """獲取 Firebase API Key"""
        if FIREBASE_FUNCTIONS and firebase_config:
            try:
                return firebase_config().firebase.api_key
            except:
                pass
        return os.getenv("FIREBASE_API_KEY")
    
    @staticmethod
    def get_firebase_auth_domain():
        """獲取 Firebase Auth Domain"""
        if FIREBASE_FUNCTIONS and firebase_config:
            try:
                return firebase_config().firebase.auth_domain
            except:
                pass
        return os.getenv("FIREBASE_AUTH_DOMAIN")
    
    # OpenAI 配置
    @staticmethod
    def get_openai_api_key():
        """獲取 OpenAI API Key"""
        if FIREBASE_FUNCTIONS and firebase_config:
            try:
                return firebase_config().openai.api_key
            except:
                pass
        return os.getenv("OPENAI_API_KEY")
    
    # reCAPTCHA 配置
    @staticmethod
    def get_recaptcha_site_key():
        """獲取 reCAPTCHA Site Key"""
        if FIREBASE_FUNCTIONS and firebase_config:
            try:
                return firebase_config().recaptcha.site_key
            except:
                pass
        return os.getenv("RECAPTCHA_SITE_KEY", "")
    
    @staticmethod
    def get_recaptcha_secret_key():
        """獲取 reCAPTCHA Secret Key"""
        if FIREBASE_FUNCTIONS and firebase_config:
            try:
                return firebase_config().recaptcha.secret_key
            except:
                pass
        return os.getenv("RECAPTCHA_SECRET_KEY", "")
    
    # Firebase 項目配置（固定值）
    FIREBASE_PROJECT_ID = "book-exchange-d4351"
    FIREBASE_DATABASE_URL = "book-exchange-d4351.firebaseio.com"
    FIREBASE_STORAGE_BUCKET = "book-exchange-d4351.firebasestorage.app"
    FIREBASE_MESSAGING_SENDER_ID = "375180204433"
    FIREBASE_APP_ID = "1:375180204433:web:294275511fdf0e06f62230"
    FIREBASE_MEASUREMENT_ID = "G-0948E45QN6"
    
    # 時區配置
    TIMEZONE_OFFSET_HOURS = 8  # UTC+8

