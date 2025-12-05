"""
這是一個包裝器，用於將原始 app.py 適配到 Firebase Functions
由於原始 app.py 文件很大，這個文件提供了兩種方案：
1. 直接導入原始 app.py（需要調整路徑）
2. 提供重構建議
"""

import sys
import os

# 添加項目根目錄到路徑
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# 方案 1：直接導入原始 app.py（簡單但不推薦用於生產環境）
try:
    # 注意：這需要確保 app.py 中的初始化代碼不會在導入時執行
    # 或者需要修改 app.py 以支持條件初始化
    from app import app as flask_app
    print("成功導入原始 Flask 應用")
except ImportError as e:
    print(f"導入原始應用失敗: {e}")
    print("請使用重構後的模塊化結構")
    flask_app = None

# 方案 2：使用重構後的模塊（推薦）
# 如果已經重構，取消下面的註釋：
# from app import create_app
# flask_app = create_app()

def get_app():
    """獲取 Flask 應用實例"""
    if flask_app is None:
        raise RuntimeError("Flask 應用未正確初始化")
    return flask_app


