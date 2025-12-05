"""
書籍相關路由
處理書籍的 CRUD 操作、搜尋、推薦等功能
"""
from flask import Blueprint, render_template, redirect, session, jsonify, request
from datetime import datetime
from app.utils.firebase import get_db
from app.utils.helpers import convert_to_utc8

books_bp = Blueprint('books', __name__)

def process_book_data(book_dict):
    """處理書籍資料，添加必要的欄位"""
    db = get_db()
    
    # 處理時間戳記（轉換為 UTC+8）
    if "created_at" in book_dict and book_dict["created_at"]:
        try:
            dt = None
            if hasattr(book_dict["created_at"], "strftime"):
                dt = book_dict["created_at"]
            elif hasattr(book_dict["created_at"], "timestamp"):
                dt = book_dict["created_at"].to_datetime()
            else:
                # 嘗試解析字符串
                try:
                    created_at_str = str(book_dict["created_at"])
                    if len(created_at_str) >= 16:
                        dt = datetime.strptime(created_at_str[:16], "%Y-%m-%d %H:%M")
                    elif len(created_at_str) >= 10:
                        dt = datetime.strptime(created_at_str[:10], "%Y-%m-%d")
                except:
                    pass
            
            if dt:
                # 轉換為 UTC+8
                dt_utc8 = convert_to_utc8(dt)
                book_dict["created_at"] = dt_utc8.strftime("%Y-%m-%d %H:%M:%S")
                book_dict["created_at_timestamp"] = dt_utc8
            else:
                book_dict["created_at"] = str(book_dict["created_at"])
                book_dict["created_at_timestamp"] = book_dict["created_at"]
        except Exception as e:
            print(f"處理時間戳記時發生錯誤：{e}")
            book_dict["created_at"] = str(book_dict["created_at"])
            book_dict["created_at_timestamp"] = book_dict["created_at"]
    else:
        book_dict["created_at"] = ""
        book_dict["created_at_timestamp"] = ""
    
    # 獲取評價資訊以顯示評分
    evaluation_id = book_dict.get("evaluation_id", "")
    if evaluation_id:
        try:
            eval_ref = db.collection("evaluations").document(evaluation_id)
            eval_doc = eval_ref.get()
            if eval_doc.exists:
                eval_dict = eval_doc.to_dict()
                book_dict["rating"] = eval_dict.get("rating", 0)
            else:
                book_dict["rating"] = 0
        except:
            book_dict["rating"] = 0
    else:
        book_dict["rating"] = 0
    
    # 處理賣家電子郵件顯示
    seller_email = book_dict.get("seller_email", "")
    if seller_email:
        if "@" in seller_email:
            book_dict["seller_display"] = seller_email.split("@")[0]
        else:
            book_dict["seller_display"] = seller_email
    else:
        book_dict["seller_display"] = "未知"
    
    # 如果沒有封面圖片，使用預設圖片路徑
    if not book_dict.get("front_image"):
        book_dict["front_image"] = "static/images/book_original.png"
    
    return book_dict

@books_bp.route("/")
def home():
    """首頁"""
    if "user" not in session:
        return redirect("/login")  # 未登入->登入頁面
    
    # 首頁只顯示初始結構，書籍通過 AJAX 載入
    return render_template("index.html", books=[])

@books_bp.route("/api/recommended_books", methods=["GET"])
def get_recommended_books():
    """獲取推薦書籍（基於用戶的「我要換書」和收藏）"""
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        db = get_db()
        current_user = session["user"]
        recommended_books = []
        
        # 獲取用戶的「我要換書」列表
        wanted_books_ref = db.collection("wanted_books")
        wanted_books_query = wanted_books_ref.where("requester_email", "==", current_user).limit(20)
        wanted_books = wanted_books_query.stream()
        
        # 收集用戶想要的書籍關鍵字（書名、作者、ISBN）
        wanted_keywords = set()
        for wanted_book in wanted_books:
            wanted_dict = wanted_book.to_dict()
            if wanted_dict.get("book_title"):
                wanted_keywords.add(wanted_dict["book_title"].lower())
            if wanted_dict.get("author"):
                wanted_keywords.add(wanted_dict["author"].lower())
            if wanted_dict.get("isbn"):
                wanted_keywords.add(wanted_dict["isbn"].lower())
        
        # 獲取用戶的收藏列表
        favorites_ref = db.collection("favorites")
        favorites_query = favorites_ref.where("user_email", "==", current_user).limit(20)
        favorites = favorites_query.stream()
        
        favorite_book_ids = set()
        favorite_keywords = set()
        for favorite in favorites:
            fav_dict = favorite.to_dict()
            book_id = fav_dict.get("book_id")
            if book_id:
                favorite_book_ids.add(book_id)
                # 獲取收藏書籍的資訊來提取關鍵字
                book_ref = db.collection("books").document(book_id)
                book_doc = book_ref.get()
                if book_doc.exists:
                    book_data = book_doc.to_dict()
                    if book_data.get("title"):
                        favorite_keywords.add(book_data["title"].lower())
                    if book_data.get("author"):
                        favorite_keywords.add(book_data["author"].lower())
        
        # 合併關鍵字
        all_keywords = wanted_keywords.union(favorite_keywords)
        
        # 查詢所有可用的書籍
        books_ref = db.collection("books")
        books_query = books_ref.where("status", "==", "available").limit(200)
        books = books_query.stream()
        
        recommended_candidates = []
        other_books = []
        
        for book in books:
            book_dict = book.to_dict()
            book_dict["id"] = book.id
            
            # 過濾掉當前用戶的書籍
            seller_email = book_dict.get("seller_email", "")
            if seller_email == current_user:
                continue
            
            # 處理書籍資料
            book_dict = process_book_data(book_dict)
            
            # 檢查是否匹配關鍵字
            title = book_dict.get("title", "").lower()
            author = book_dict.get("author", "").lower()
            isbn = book_dict.get("isbn", "").lower()
            
            is_recommended = False
            if all_keywords:
                for keyword in all_keywords:
                    if keyword in title or keyword in author or keyword in isbn:
                        is_recommended = True
                        break
            
            if is_recommended:
                recommended_candidates.append(book_dict)
            else:
                other_books.append(book_dict)
        
        # 按創建時間排序
        recommended_candidates.sort(key=lambda x: x.get("created_at_timestamp", ""), reverse=True)
        other_books.sort(key=lambda x: x.get("created_at_timestamp", ""), reverse=True)
        
        # 合併推薦書籍和其他書籍（推薦書籍在前）
        recommended_books = recommended_candidates + other_books
        
        # 記錄已返回的書籍ID，避免重複
        returned_book_ids = set()
        unique_recommended = []
        for book in recommended_books:
            if book["id"] not in returned_book_ids:
                unique_recommended.append(book)
                returned_book_ids.add(book["id"])
                if len(unique_recommended) >= 10:
                    break
        
        return jsonify({
            "success": True,
            "books": unique_recommended,
            "has_more": len(recommended_books) > len(unique_recommended)
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"獲取推薦書籍時發生錯誤：{e}")
        return jsonify({"success": False, "error": str(e)}), 500

# TODO: 遷移以下路由從 app.py：
# - /api/books
# - /book/<book_id>
# - /add_book
# - /edit_book/<book_id>
# - /delete_book/<book_id>
# - /write_review
# - /edit_review/<review_id>
# - /delete_review/<review_id>
# - /google_books_search
# - /api/google_books/search
# - /google_book/<google_id>
# - /search
# - /ai_recommend
# - /wanted_book
# - /wanted_book/<wanted_book_id>
# - /edit_wanted_book/<wanted_book_id>
# - /delete_wanted_book/<wanted_book_id>
# - /collects
# - /api/favorite/<item_id> (POST/DELETE)
# - /api/favorite/<item_id>/check

