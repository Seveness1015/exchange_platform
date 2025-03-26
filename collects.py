from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# 設定 PostgreSQL 連線
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://username:password@localhost:5432/book_exchange'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# 定義收藏資料表
class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    book_id = db.Column(db.Integer, nullable=False)

# 書籍資料表 (只提供查詢)
class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    image_url = db.Column(db.String(255), nullable=False)

# 取得使用者收藏的書籍
@app.route('/favorites', methods=['GET'])
def get_favorites():
    user_id = 1  # 假設是登入使用者 ID
    favorites = db.session.query(Favorite, Book).join(Book, Favorite.book_id == Book.id).filter(Favorite.user_id == user_id).all()
    
    result = [{"id": fav.Favorite.book_id, "name": fav.Book.name, "image_url": fav.Book.image_url} for fav in favorites]
    return jsonify(result)

# 刪除收藏
@app.route('/favorites/<int:book_id>', methods=['DELETE'])
def remove_favorite(book_id):
    user_id = 1  # 假設是登入使用者 ID
    favorite = Favorite.query.filter_by(user_id=user_id, book_id=book_id).first()
    
    if favorite:
        db.session.delete(favorite)
        db.session.commit()
        return jsonify({"message": "已取消收藏"}), 200
    return jsonify({"error": "收藏不存在"}), 404

if __name__ == '__main__':
    app.run(debug=True)
