"""
Flask 應用工廠
創建和配置 Flask 應用實例
"""
from flask import Flask
from app.config import Config
from app.utils.firebase import init_firebase
from app.utils.ai import init_openai


def create_app(config_class=Config):
    """
    創建 Flask 應用實例
    
    Args:
        config_class: 配置類（默認為 Config）
    
    Returns:
        Flask 應用實例
    """
    app = Flask(__name__, 
                template_folder='../templates',
                static_folder='../static')
    
    # 載入配置
    app.config['SECRET_KEY'] = config_class.SECRET_KEY
    
    # 初始化 Firebase
    init_firebase()
    
    # 初始化 OpenAI
    init_openai()
    
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

