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

# 設置標誌，告訴應用我們在 Firebase Functions 環境中
os.environ['FIREBASE_FUNCTIONS'] = '1'

# 從應用工廠創建應用
try:
    from app import create_app
    app = create_app()
    
    # 包裝應用以適配 Firebase Functions
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    
    print("✓ Flask 應用已成功從應用工廠創建")
    
except ImportError as e:
    print(f"導入應用失敗: {e}")
    import traceback
    traceback.print_exc()
    print("嘗試使用原始 app.py...")
    
    # 回退到原始 app.py（如果存在）
    try:
        from app import app as flask_app
        app = flask_app
        print("✓ 使用原始 app.py")
    except ImportError:
        print("無法導入應用，創建錯誤應用")
        # 創建一個簡單的錯誤應用
        from flask import Flask
        app = Flask(__name__)
        
        @app.route('/')
        def error():
            return "應用導入失敗，請檢查部署配置。請確保已完成路由遷移。", 500

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
