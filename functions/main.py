"""
Firebase Functions 入口點
這個文件將 Flask 應用適配到 Firebase Functions
"""

import sys
import os

# 添加項目根目錄到 Python 路徑
# 這樣可以導入項目根目錄的模塊
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

# 設置環境變數（Firebase Functions 會自動提供）
# 確保 Firebase 憑證可以正確加載
if 'GOOGLE_APPLICATION_CREDENTIALS' not in os.environ:
    # 如果沒有設置，嘗試使用項目根目錄的 firebase_config.json
    config_path = os.path.join(parent_dir, 'firebase_config.json')
    if os.path.exists(config_path):
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = config_path

# 導入 Flask 應用
# 注意：這需要修改原始 app.py 以支持條件運行
try:
    # 設置標誌，告訴 app.py 我們在 Firebase Functions 環境中
    os.environ['FIREBASE_FUNCTIONS'] = '1'
    
    # 導入原始應用
    from app import app
    
    # 包裝應用以適配 Firebase Functions
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    
except ImportError as e:
    print(f"導入應用失敗: {e}")
    print("請確保 app.py 在項目根目錄中")
    # 創建一個簡單的錯誤應用
    from flask import Flask
    app = Flask(__name__)
    
    @app.route('/')
    def error():
        return "應用導入失敗，請檢查部署配置", 500

# Firebase Functions HTTP 觸發器
import functions_framework

@functions_framework.http
def app_handler(request):
    """
    Firebase Functions HTTP 觸發器
    這個函數處理所有 HTTP 請求
    """
    with app.app_context():
        return app.full_dispatch_request()
