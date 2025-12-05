"""
本地開發運行腳本
使用應用工廠創建 Flask 應用並運行
"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    # 允許從其他設備訪問（手機測試）
    # host='0.0.0.0' 表示監聽所有網路介面
    # 在手機瀏覽器中訪問: http://你的電腦IP:5000
    app.run(host='0.0.0.0', port=5000, debug=True)

