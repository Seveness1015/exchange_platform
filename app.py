import firebase_admin
import pyrebase
from firebase_admin import credentials, firestore, storage
from flask import Flask, render_template, request, redirect, session,jsonify
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
import os
import requests
from PIL import Image
import io
import uuid
# 嘗試導入 OpenAI（如果未安裝則使用規則生成）
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("警告：未安裝 openai 套件，將使用規則生成推薦。請執行 'pip install openai' 安裝。")

app = Flask(__name__)
app.secret_key = "supersecretkey"

# 初始化 Firebase Admin
cred = credentials.Certificate("firebase_config.json")
firebase_admin.initialize_app(cred)
db = firestore.client()
load_dotenv()

firebase_api_key = os.getenv("FIREBASE_API_KEY")
firebase_auth_domain = os.getenv("FIREBASE_AUTH_DOMAIN")

# 初始化 OpenAI 客戶端
openai_api_key = os.getenv("OPENAI_API_KEY")
if openai_api_key and OPENAI_AVAILABLE:
    try:
        openai_client = OpenAI(api_key=openai_api_key)
        print("✓ OpenAI API 客戶端初始化成功")
    except Exception as e:
        openai_client = None
        print(f"警告：OpenAI 客戶端初始化失敗：{e}，將使用規則生成推薦")
else:
    openai_client = None
    if not OPENAI_AVAILABLE:
        print("警告：未安裝 openai 套件，將使用規則生成推薦")
    elif not openai_api_key:
        print("警告：未設置 OPENAI_API_KEY，將使用規則生成推薦")

# 初始化 Pyrebase（用於身份驗證）
firebase_config = {
    "apiKey": firebase_api_key,
    "authDomain": firebase_auth_domain,
    "databaseURL": "book-exchange-d4351.firebaseio.com",
    "projectId": "book-exchange-d4351",
    "storageBucket": "book-exchange-d4351.firebasestorage.app",
    "messagingSenderId": "375180204433",
    "appId": "1:375180204433:web:294275511fdf0e06f62230",
    "measurementId": "G-0948E45QN6"
}

firebase = pyrebase.initialize_app(firebase_config)
auth_firebase = firebase.auth()


def convert_to_utc8(dt):
    """將 datetime 對象轉換為 UTC+8 時區"""
    if dt is None:
        return None
    # 如果已經是 datetime 對象，確保它是 UTC
    if isinstance(dt, datetime):
        # 如果沒有時區信息，假設是 UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        # 轉換為 UTC+8
        return dt.astimezone(timezone(timedelta(hours=8)))
    return dt


def calculate_recommendation_score(avg_rating, review_count, necessity_score, provider_count):
    """計算推薦分數（0-100）"""
    rating_score = (avg_rating / 5.0) * 40  # 評分佔 40%
    count_score = min(review_count / 10.0, 1.0) * 30  # 評價數量佔 30%
    necessity_normalized = min(max(necessity_score / 10.0, -1), 1) if necessity_score != 0 else 0
    necessity_score_normalized = ((necessity_normalized + 1) / 2) * 20  # 必要性佔 20%
    provider_score = min(provider_count / 5.0, 1.0) * 10  # 提供者數量佔 10%
    
    return rating_score + count_score + necessity_score_normalized + provider_score


def generate_ai_recommendation(book_title, reviews, avg_rating, review_count, 
                               provider_count, course_name, department, grade, 
                               additional_requirements=""):
    """
    使用 OpenAI API 生成更自然的推薦理由
    """
    # 如果沒有設置 API Key，返回 None（將使用規則生成）
    if not openai_client:
        return None
    
    # 整理評價內容
    review_summaries = []
    for review in reviews[:5]:  # 取前 5 個評價
        content = review.get("review_content", "")
        rating = review.get("rating", 0)
        if content:
            review_summaries.append(f"評分 {rating}/5：{content[:200]}")
    
    if not review_summaries:
        return None  # 如果沒有評價內容，使用規則生成
    
    reviews_text = "\n".join(review_summaries)
    
    # 構建提示詞
    grade_text = f"{grade}的" if grade else ""
    dept_text = f"{department}" if department else "學生"
    
    prompt = f"""你是一位友善的學長姐，正在為一位{grade_text}{dept_text}推薦「{course_name}」這門課的教科書。

書籍名稱：{book_title}
平均評分：{avg_rating:.1f}/5.0
評價數量：{review_count} 則
平台提供者數量：{provider_count} 人

以下是學長姐們的評價：
{reviews_text}

請用親切、自然的語氣（就像在跟學弟妹聊天一樣），為這位學生寫一段推薦理由（約 150-200 字），包括：
1. 這本書是否必要購買
2. 為什麼推薦（或不推薦）
3. 學長姐們的評價重點
4. 購買建議

請用繁體中文回答，語氣要親切自然，就像學長姐在給建議一樣。不要使用列表格式，用流暢的段落文字表達。"""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "你是一位友善的學長姐，正在為學弟妹推薦教科書。你的回答要親切、自然，就像在跟朋友聊天一樣。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=400,
            temperature=0.7
        )
        
        ai_recommendation = response.choices[0].message.content.strip()
        
        # 計算必要性等級（基於評分和評價內容）
        if avg_rating >= 4.5:
            necessity_level = "非常必要"
        elif avg_rating >= 4.0:
            necessity_level = "必要"
        elif avg_rating >= 3.5:
            necessity_level = "可選"
        else:
            necessity_level = "不必要"
        
        return {
            "recommendation_text": ai_recommendation,
            "summary": ai_recommendation,  # 為了與模板兼容
            "generated_by": "ai",
            "necessity_level": necessity_level,
            "avg_rating": avg_rating,
            "review_count": review_count,
            "provider_count": provider_count,
            "recommendation_score": calculate_recommendation_score(avg_rating, review_count, 0, provider_count),
            "key_reviews": []
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"OpenAI API 調用失敗：{e}")
        # 回退到規則生成
        return None


def generate_human_recommendation(book_title, reviews, avg_rating, review_count, 
                                  provider_count, course_name, department, grade, 
                                  additional_requirements=""):
    """
    生成人性化的推薦理由（規則生成，作為備用方案）
    """
    # 分析評價內容
    positive_keywords = {
        "必買": 3, "必備": 3, "需要": 2, "推薦": 2, "好用": 2, 
        "實用": 2, "重要": 2, "幫助": 1, "清楚": 1, "易懂": 1
    }
    negative_keywords = {
        "不需要": -3, "不必要": -3, "不用": -2, "沒用": -2, 
        "浪費": -2, "難懂": -1, "複雜": -1
    }
    
    # 計算必要性分數
    necessity_score = 0
    keyword_mentions = []
    
    for review in reviews:
        content = (review.get("review_content", "") or "").lower()
        for keyword, weight in positive_keywords.items():
            if keyword in content:
                necessity_score += weight
                keyword_mentions.append(keyword)
        for keyword, weight in negative_keywords.items():
            if keyword in content:
                necessity_score += weight
    
    # 生成推薦理由
    reasons = []
    
    # 1. 必要性描述
    if necessity_score >= 5:
        necessity_desc = "非常必要"
        reason_text = f"根據 {review_count} 位學長姐的評價，這本書對於「{course_name}」這門課來說是**非常必要的**。"
    elif necessity_score >= 2:
        necessity_desc = "必要"
        reason_text = f"根據 {review_count} 位學長姐的評價，這本書對於「{course_name}」這門課來說是**必要的**。"
    elif necessity_score >= -1:
        necessity_desc = "可選"
        reason_text = f"根據 {review_count} 位學長姐的評價，這本書對於「{course_name}」這門課來說是**可選的**，可以根據個人需求決定。"
    else:
        necessity_desc = "不必要"
        reason_text = f"根據 {review_count} 位學長姐的評價，這本書對於「{course_name}」這門課來說**可能不是必要的**。"
    
    reasons.append(reason_text)
    
    # 2. 評分描述
    if avg_rating >= 4.5:
        rating_desc = f"這本書獲得了**{avg_rating:.1f} 分**的高評價（滿分 5 分），學長姐們普遍認為這本書非常值得推薦。"
    elif avg_rating >= 4.0:
        rating_desc = f"這本書獲得了**{avg_rating:.1f} 分**的好評（滿分 5 分），大部分學長姐都給予正面評價。"
    elif avg_rating >= 3.5:
        rating_desc = f"這本書獲得了**{avg_rating:.1f} 分**的評價（滿分 5 分），評價較為中肯。"
    elif avg_rating >= 3.0:
        rating_desc = f"這本書獲得了**{avg_rating:.1f} 分**的評價（滿分 5 分），評價較為一般。"
    else:
        rating_desc = f"這本書獲得了**{avg_rating:.1f} 分**的評價（滿分 5 分），評價較低。"
    
    reasons.append(rating_desc)
    
    # 3. 評價數量描述
    if review_count >= 10:
        count_desc = f"目前已經有**{review_count} 位學長姐**為這本書寫過評價，評價數量相當豐富，可以作為很好的參考。"
    elif review_count >= 5:
        count_desc = f"目前已經有**{review_count} 位學長姐**為這本書寫過評價，可以作為參考。"
    elif review_count >= 2:
        count_desc = f"目前已經有**{review_count} 位學長姐**為這本書寫過評價。"
    else:
        count_desc = f"目前只有**{review_count} 位學長姐**為這本書寫過評價，評價較少。"
    
    reasons.append(count_desc)
    
    # 4. 提供者描述
    if provider_count >= 5:
        provider_desc = f"好消息！目前平台上有**{provider_count} 位同學**正在提供這本書，選擇很多，價格也比較有競爭力。"
    elif provider_count >= 2:
        provider_desc = f"目前平台上有**{provider_count} 位同學**正在提供這本書，可以比較一下價格和書況。"
    elif provider_count == 1:
        provider_desc = f"目前平台上有**{provider_count} 位同學**正在提供這本書，要買要快！"
    else:
        provider_desc = f"目前平台上**暫時沒有人提供**這本書，你可以考慮發布「我想要書」的需求，或者等待其他同學提供。"
    
    reasons.append(provider_desc)
    
    # 5. 系所/年級匹配描述
    if department:
        dept_desc = f"特別提醒：如果你就讀**{department}**"
        if grade:
            dept_desc += f"**{grade}**"
        dept_desc += "，這本書的評價對你來說會更有參考價值。"
        reasons.append(dept_desc)
    
    # 6. 額外要求描述
    if additional_requirements:
        additional_desc = f"另外，根據你提到的「{additional_requirements}」，這本書可能符合你的需求，建議你可以參考學長姐的評價來判斷。"
        reasons.append(additional_desc)
    
    # 7. 評價內容摘要（提取關鍵評價）
    key_reviews = []
    for review in reviews[:3]:  # 取前 3 個評價
        content = review.get("review_content", "")
        if content and len(content) > 20:
            # 截取前 100 字
            excerpt = content[:100] + "..." if len(content) > 100 else content
            reviewer_email = review.get("reviewer_email", "")
            reviewer = reviewer_email.split("@")[0] if "@" in reviewer_email else "匿名"
            key_reviews.append({
                "rating": review.get("rating", 0),
                "content": excerpt,
                "reviewer": reviewer
            })
    
    # 7. 生成完整的推薦文字
    full_recommendation = {
        "necessity_level": necessity_desc,
        "summary": " ".join(reasons),
        "key_reviews": key_reviews,
        "recommendation_score": calculate_recommendation_score(avg_rating, review_count, necessity_score, provider_count),
        "avg_rating": avg_rating,
        "review_count": review_count,
        "provider_count": provider_count,
        "generated_by": "rule"
    }
    
    return full_recommendation


def get_message_sort_key(msg):
    """獲取訊息的排序鍵，用於按時間排序（正確處理 Firestore Timestamp）"""
    created_at = msg.get("created_at")
    if not created_at:
        return datetime.min
    
    # 處理 Firestore Timestamp
    if hasattr(created_at, "to_datetime"):
        try:
            return created_at.to_datetime()
        except:
            return datetime.min
    elif hasattr(created_at, "timestamp"):
        try:
            return datetime.fromtimestamp(created_at.timestamp())
        except:
            return datetime.min
    # 如果已經是 datetime 對象
    elif hasattr(created_at, "strftime"):
        return created_at
    # 如果是字符串，嘗試解析
    elif isinstance(created_at, str) and created_at:
        try:
            # 嘗試解析 "YYYY-MM-DD HH:MM" 格式
            return datetime.strptime(created_at[:16], "%Y-%m-%d %H:%M")
        except:
            try:
                # 嘗試解析 "YYYY-MM-DD" 格式
                return datetime.strptime(created_at[:10], "%Y-%m-%d")
            except:
                return datetime.min
    else:
        return datetime.min


@app.route("/")
def home():
    if "user" not in session:
        return redirect("/login")  # 未登入->登入頁面
    
    # 首頁只顯示初始結構，書籍通過 AJAX 載入
    return render_template("index.html", books=[])

# 獲取推薦書籍（基於用戶的「我要換書」和收藏）
@app.route("/api/recommended_books", methods=["GET"])
def get_recommended_books():
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
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

# 獲取更多書籍（分頁）
@app.route("/api/books", methods=["GET"])
def get_books():
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        current_user = session["user"]
        page = int(request.args.get("page", 1))
        page_size = 10
        offset = (page - 1) * page_size
        
        # 查詢所有可用的書籍
        books_ref = db.collection("books")
        books_query = books_ref.where("status", "==", "available").limit(200)
        books = books_query.stream()
        
        books_list = []
        for book in books:
            book_dict = book.to_dict()
            book_dict["id"] = book.id
            
            # 過濾掉當前用戶的書籍
            seller_email = book_dict.get("seller_email", "")
            if seller_email == current_user:
                continue
            
            # 處理書籍資料
            book_dict = process_book_data(book_dict)
            books_list.append(book_dict)
        
        # 按創建時間排序
        books_list.sort(key=lambda x: x.get("created_at_timestamp", ""), reverse=True)
        
        # 分頁
        total = len(books_list)
        paginated_books = books_list[offset:offset + page_size]
        
        return jsonify({
            "success": True,
            "books": paginated_books,
            "page": page,
            "page_size": page_size,
            "total": total,
            "has_more": offset + page_size < total
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"獲取書籍時發生錯誤：{e}")
        return jsonify({"success": False, "error": str(e)}), 500

# 處理書籍資料的輔助函數
def process_book_data(book_dict):
    """處理書籍資料，添加必要的欄位"""
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

# 收藏書籍或換書資訊
@app.route("/api/favorite/<item_id>", methods=["POST"])
def add_favorite(item_id):
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        current_user = session["user"]
        item_type = request.args.get("type", "book")  # "book" 或 "wanted_book"
        
        # 檢查項目是否存在
        if item_type == "wanted_book":
            item_ref = db.collection("wanted_books").document(item_id)
        else:
            item_ref = db.collection("books").document(item_id)
        
        item_doc = item_ref.get()
        if not item_doc.exists:
            return jsonify({"success": False, "error": "項目不存在"}), 404
        
        # 檢查是否已經收藏
        favorites_ref = db.collection("favorites")
        favorites_query = favorites_ref.where("user_email", "==", current_user).where("item_id", "==", item_id).where("item_type", "==", item_type).limit(1)
        existing = list(favorites_query.stream())
        
        if existing:
            return jsonify({"success": True, "message": "已經收藏"})
        
        # 添加收藏
        favorite_data = {
            "user_email": current_user,
            "item_id": item_id,
            "item_type": item_type,  # "book" 或 "wanted_book"
            "created_at": firestore.SERVER_TIMESTAMP
        }
        favorites_ref.add(favorite_data)
        
        return jsonify({"success": True, "message": "收藏成功"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

# 取消收藏
@app.route("/api/favorite/<item_id>", methods=["DELETE"])
def remove_favorite(item_id):
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        current_user = session["user"]
        item_type = request.args.get("type", "book")  # "book" 或 "wanted_book"
        
        # 查找並刪除收藏
        favorites_ref = db.collection("favorites")
        favorites_query = favorites_ref.where("user_email", "==", current_user).where("item_id", "==", item_id).where("item_type", "==", item_type).limit(1)
        favorites = list(favorites_query.stream())
        
        if favorites:
            favorites[0].reference.delete()
            return jsonify({"success": True, "message": "取消收藏成功"})
        else:
            return jsonify({"success": False, "error": "未找到收藏記錄"}), 404
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

# 檢查是否已收藏
@app.route("/api/favorite/<item_id>/check", methods=["GET"])
def check_favorite(item_id):
    if "user" not in session:
        return jsonify({"success": False, "is_favorited": False}), 401
    
    try:
        current_user = session["user"]
        item_type = request.args.get("type", "book")  # "book" 或 "wanted_book"
        favorites_ref = db.collection("favorites")
        favorites_query = favorites_ref.where("user_email", "==", current_user).where("item_id", "==", item_id).where("item_type", "==", item_type).limit(1)
        favorites = list(favorites_query.stream())
        
        return jsonify({"success": True, "is_favorited": len(favorites) > 0})
    except Exception as e:
        return jsonify({"success": False, "is_favorited": False}), 500


# 註冊
@app.route("/register", methods=["GET", "POST"])
def register():
    # 獲取 reCAPTCHA Site Key（用於前端顯示）
    recaptcha_site_key = os.getenv("RECAPTCHA_SITE_KEY", "")
    recaptcha_secret_key = os.getenv("RECAPTCHA_SECRET_KEY", "")
    
    if request.method == "POST":
        std_num = request.form.get("std_num", "").strip()
        password = request.form.get("password", "")
        password_check = request.form.get("password-check", "")
        recaptcha_response = request.form.get("g-recaptcha-response", "")

        # 驗證 reCAPTCHA
        if recaptcha_secret_key:
            if not recaptcha_response:
                return render_template("register.html", error="請完成 reCAPTCHA 驗證", recaptcha_site_key=recaptcha_site_key)
            
            # 驗證 reCAPTCHA 響應
            recaptcha_verify_url = "https://www.google.com/recaptcha/api/siteverify"
            recaptcha_data = {
                "secret": recaptcha_secret_key,
                "response": recaptcha_response
            }
            
            try:
                recaptcha_result = requests.post(recaptcha_verify_url, data=recaptcha_data, timeout=10)
                recaptcha_result.raise_for_status()
                recaptcha_json = recaptcha_result.json()
                
                if not recaptcha_json.get("success", False):
                    return render_template("register.html", error="reCAPTCHA 驗證失敗，請重試", recaptcha_site_key=recaptcha_site_key)
            except Exception as recaptcha_error:
                print(f"reCAPTCHA 驗證時發生錯誤: {recaptcha_error}")
                return render_template("register.html", error="reCAPTCHA 驗證時發生錯誤，請稍後再試", recaptcha_site_key=recaptcha_site_key)

        # 驗證輸入
        if not std_num:
            return render_template("register.html", error="請輸入學號", recaptcha_site_key=recaptcha_site_key)
        
        if not password:
            return render_template("register.html", error="請輸入密碼", recaptcha_site_key=recaptcha_site_key)
        
        if password != password_check:
            return render_template("register.html", error="兩次輸入的密碼不一致", recaptcha_site_key=recaptcha_site_key)
        
        # 驗證密碼規則
        if len(password) < 6:
            return render_template("register.html", error="密碼長度至少6位", recaptcha_site_key=recaptcha_site_key)
        
        if not any(c.isupper() for c in password):
            return render_template("register.html", error="密碼至少包含一個大寫字母", recaptcha_site_key=recaptcha_site_key)
        
        if not any(c.islower() for c in password):
            return render_template("register.html", error="密碼至少包含一個小寫字母", recaptcha_site_key=recaptcha_site_key)

        email = std_num + "@mail.ntust.edu.tw"

        try:
            # 創建 Firebase 使用者
            user = auth_firebase.create_user_with_email_and_password(email, password)
            print(f"User created successfully: {user['localId']}")
            print(f"User email: {email}")
            print(f"User idToken exists: {'idToken' in user}")

            # 讓 Firebase 直接發送驗證信
            # 注意：send_email_verification 需要有效的 idToken
            try:
                if 'idToken' not in user:
                    print("Warning: idToken not found in user object, attempting to sign in first...")
                    # 如果沒有 idToken，先登入獲取
                    user = auth_firebase.sign_in_with_email_and_password(email, password)
                    print("User signed in successfully to get idToken")
                
                auth_firebase.send_email_verification(user['idToken'])
                print(f"Verification email sent successfully to {email}!")
            except Exception as email_error:
                import traceback
                error_msg = str(email_error)
                print(f"Error sending verification email: {error_msg}")
                traceback.print_exc()
                
                # 嘗試替代方法：先登入再發送驗證郵件
                try:
                    print("Attempting alternative method: sign in then send verification...")
                    signed_in_user = auth_firebase.sign_in_with_email_and_password(email, password)
                    auth_firebase.send_email_verification(signed_in_user['idToken'])
                    print(f"Verification email sent via alternative method to {email}!")
                except Exception as alt_error:
                    print(f"Alternative method also failed: {alt_error}")
                    # 即使發送郵件失敗，用戶已創建成功，所以仍然顯示成功訊息
                    # 但可以提示用戶稍後手動請求驗證郵件
                    return render_template("register.html", 
                                         email=True, 
                                         email_warning="帳號已創建，但驗證郵件發送可能失敗，請稍後在登入頁面重新發送驗證郵件。")

            return render_template("register.html", email=True, recaptcha_site_key=recaptcha_site_key)
        except Exception as e:
            import traceback
            error_msg = str(e)
            print(f"Registration Error: {error_msg}")
            traceback.print_exc()
            
            # 提供更詳細的錯誤訊息
            if "EMAIL_EXISTS" in error_msg or "email-already-exists" in error_msg.lower():
                return render_template("register.html", error="該學號已被註冊，請使用其他學號。", recaptcha_site_key=recaptcha_site_key)
            elif "INVALID_EMAIL" in error_msg or "invalid-email" in error_msg.lower():
                return render_template("register.html", error="電子郵件格式無效。", recaptcha_site_key=recaptcha_site_key)
            elif "WEAK_PASSWORD" in error_msg or "weak-password" in error_msg.lower():
                return render_template("register.html", error="密碼強度不足，請使用更強的密碼。", recaptcha_site_key=recaptcha_site_key)
            else:
                return render_template("register.html", error=f"註冊失敗：{error_msg}", recaptcha_site_key=recaptcha_site_key)

    return render_template("register.html", recaptcha_site_key=recaptcha_site_key)


# 登入
@app.route("/login", methods=["GET", "POST"])
def login():
    if "user" in session:
        return redirect("/")  # 已登入則跳轉到首頁
    
    if request.method == "POST":
        std_num = request.form.get("std_num", "").strip()
        password = request.form.get("password", "")
        
        if not std_num or not password:
            return render_template("login.html", error=True)
        
        email = std_num + "@mail.ntust.edu.tw"

        try:
            user = auth_firebase.sign_in_with_email_and_password(email, password)

            # 檢查是否已驗證
            user_info = auth_firebase.get_account_info(user['idToken'])
            if not user_info['users'][0]['emailVerified']:
                return render_template("login.html", no_email=True)

            # 標準化 email（轉為小寫並去除空格，確保一致性）
            session["user"] = email.strip().lower()
            return redirect("/")
        except Exception as e:
            error_msg = str(e)
            # 提供更友好的錯誤訊息
            if "INVALID_PASSWORD" in error_msg or "wrong-password" in error_msg.lower():
                return render_template("login.html", error=True)
            elif "EMAIL_NOT_FOUND" in error_msg or "user-not-found" in error_msg.lower():
                return render_template("login.html", error=True)
            else:
                return render_template("login.html", error=True)

    return render_template("login.html")

# 忘記密碼
@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if "user" in session:
        return redirect("/")  # 已登入則跳轉到首頁
    
    if request.method == "POST":
        std_num = request.form.get("std_num", "").strip()
        
        if not std_num:
            return render_template("forgot_password.html", error="請輸入學號。")
        
        email = std_num + "@mail.ntust.edu.tw"
        
        try:
            # 使用 Firebase Auth 發送密碼重設郵件
            auth_firebase.send_password_reset_email(email)
            return render_template("forgot_password.html", success=True)
        except Exception as e:
            error_msg = str(e)
            # 提供更友好的錯誤訊息
            if "EMAIL_NOT_FOUND" in error_msg or "user-not-found" in error_msg.lower():
                return render_template("forgot_password.html", error="找不到此學號的帳號，請確認學號是否正確。")
            elif "too-many-requests" in error_msg.lower():
                return render_template("forgot_password.html", error="請求過於頻繁，請稍後再試。")
            else:
                return render_template("forgot_password.html", error="發送郵件失敗，請稍後再試。")
    
    return render_template("forgot_password.html")


# 登出
@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")  


# 個人頁面
@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user" not in session:
        return redirect("/login")  # 未登入則跳轉到登入頁
    
    try:
        current_user = session["user"]
        view_user = request.args.get("user", current_user)  # 預設查看當前用戶，也可以查看其他用戶
        
        # 確保 view_user 是有效的 email 地址
        if not view_user or view_user.strip() == "":
            view_user = current_user
        
        # 標準化 email 以確保正確比較（轉為小寫並去除空格）
        current_user_normalized = current_user.strip().lower() if current_user else ""
        view_user_normalized = view_user.strip().lower() if view_user else ""
        
        # 檢查是查看自己還是其他人
        is_own_profile = (view_user_normalized == current_user_normalized)
        
        # 調試輸出：顯示用戶資訊
        print(f"個人資料頁面：current_user={current_user}, view_user={view_user}, is_own_profile={is_own_profile}")
        
        # 從 Firestore 讀取用戶顯示名稱和頭像，如果不存在則使用 email 前綴和預設頭像
        try:
            user_ref = db.collection("users").document(view_user)
            user_doc = user_ref.get()
            
            if user_doc.exists:
                user_data = user_doc.to_dict()
                user_display = user_data.get("display_name", "")
                user_avatar = user_data.get("avatar", "user_cat01.png")
                if not user_display:
                    # 如果沒有 display_name，使用 email 前綴
                    if "@" in view_user:
                        user_display = view_user.split("@")[0]
                    else:
                        user_display = view_user
            else:
                # 如果用戶資料不存在，使用 email 前綴和預設頭像
                if "@" in view_user:
                    user_display = view_user.split("@")[0]
                else:
                    user_display = view_user
                user_avatar = "user_cat01.png"
        except Exception as e:
            print(f"讀取用戶顯示名稱時發生錯誤：{e}")
            # 如果讀取失敗，使用 email 前綴和預設頭像
            if "@" in view_user:
                user_display = view_user.split("@")[0]
            else:
                user_display = view_user
            user_avatar = "user_cat01.png"
        
        # 獲取用戶的書籍（提供的）
        books_ref = db.collection("books")
        provided_books = []
        
        # 標準化 email（轉為小寫並去除空格，確保一致性）
        view_user_normalized = view_user.strip().lower() if view_user else ""
        
        try:
            # 使用簡單查詢（只查詢 seller_email），然後在 Python 中過濾和排序
            # 這樣可以避免需要 Firestore 索引
            try:
                # 先嘗試精確匹配
                books_query = books_ref.where("seller_email", "==", view_user).limit(100)
                books = books_query.stream()
                
                # 同時也查詢標準化後的 email（以防資料庫中有不同格式）
                books_query_normalized = books_ref.where("seller_email", "==", view_user_normalized).limit(100)
                books_normalized = books_query_normalized.stream()
                
                # 合併兩個查詢結果，使用 set 避免重複
                book_ids_seen = set()
                
                for book in books:
                    book_dict = book.to_dict()
                    book_id = book.id
                    
                    # 跳過重複的書籍
                    if book_id in book_ids_seen:
                        continue
                    book_ids_seen.add(book_id)
                    
                    book_dict["id"] = book_id
                    
                    # 過濾掉 status 不是 "available" 的記錄
                    status = book_dict.get("status", "available")
                    if status != "available":
                        continue
                    
                    # 標準化 seller_email 以確保匹配
                    seller_email = book_dict.get("seller_email", "").strip().lower()
                    if seller_email != view_user_normalized:
                        # 如果標準化後不匹配，跳過（除非原始 email 匹配）
                        original_seller_email = book_dict.get("seller_email", "").strip()
                        if original_seller_email != view_user.strip():
                            continue
                    
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
                    
                    # 處理圖片
                    if not book_dict.get("front_image"):
                        book_dict["front_image"] = "static/images/book_original.png"
                    
                    # 處理時間戳記（轉換為 UTC+8，用於排序）
                    if "created_at" in book_dict and book_dict["created_at"]:
                        try:
                            dt = None
                            if hasattr(book_dict["created_at"], "strftime"):
                                dt = book_dict["created_at"]
                            elif hasattr(book_dict["created_at"], "timestamp"):
                                dt = book_dict["created_at"].to_datetime()
                            
                            if dt:
                                # 轉換為 UTC+8
                                dt_utc8 = convert_to_utc8(dt)
                                created_at_str = dt_utc8.strftime("%Y-%m-%d")
                                created_at_for_sort = dt_utc8
                            else:
                                created_at_str = str(book_dict["created_at"])[:10]
                                created_at_for_sort = book_dict["created_at"]
                            
                            book_dict["created_at"] = created_at_str
                            book_dict["_created_at_for_sort"] = created_at_for_sort
                        except Exception as ts_error:
                            print(f"處理時間戳記時發生錯誤：{ts_error}")
                            book_dict["created_at"] = str(book_dict["created_at"])[:10] if book_dict["created_at"] else ""
                            book_dict["_created_at_for_sort"] = None
                    else:
                        book_dict["created_at"] = ""
                        book_dict["_created_at_for_sort"] = None
                    
                    provided_books.append(book_dict)
                
                # 按創建時間排序（降序）
                if provided_books:
                    try:
                        # 使用 _created_at_for_sort 進行排序
                        provided_books.sort(key=lambda x: x.get("_created_at_for_sort") if x.get("_created_at_for_sort") else "", reverse=True)
                        # 移除臨時排序欄位
                        for book in provided_books:
                            if "_created_at_for_sort" in book:
                                del book["_created_at_for_sort"]
                    except Exception as sort_error:
                        print(f"排序時發生錯誤：{sort_error}")
                        # 如果排序失敗，嘗試按字符串排序
                        try:
                            provided_books.sort(key=lambda x: x.get("created_at", ""), reverse=True)
                        except:
                            pass  # 如果排序失敗，保持原順序
                
                # 限制數量
                provided_books = provided_books[:50]
                print(f"找到 {len(provided_books)} 本「提供的書籍」")
                
            except Exception as query_error:
                import traceback
                traceback.print_exc()
                print(f"查詢「提供的書籍」時發生錯誤：{query_error}")
                # 如果查詢失敗，provided_books 保持為空列表
            
        except Exception as books_error:
            import traceback
            traceback.print_exc()
            print(f"查詢「提供的書籍」時發生錯誤：{books_error}")
            # 如果查詢失敗，provided_books 保持為空列表
        
        # 計算用戶平均評分（基於交易評價，即其他人在交易後對這名使用者的評分）
        avg_rating = 0
        rating_text = "0.0"
        rating_description = "尚無評價"
        
        try:
            # 從 transaction_evaluations 集合中查詢該用戶被評價的分數
            evaluations_ref = db.collection("transaction_evaluations")
            # 查詢 evaluated_email 為該用戶的所有評價
            eval_query = evaluations_ref.where("evaluated_email", "==", view_user).limit(100)
            eval_docs = list(eval_query.stream())
            
            ratings = []
            for eval_doc in eval_docs:
                eval_dict = eval_doc.to_dict()
                rating = eval_dict.get("rating", 0)
                if rating > 0:
                    ratings.append(rating)
            
            if ratings:
                avg_rating = sum(ratings) / len(ratings)
                rating_text = f"{avg_rating:.1f}"
                if avg_rating >= 4.5:
                    rating_description = "評價優秀"
                elif avg_rating >= 3.5:
                    rating_description = "評價良好"
                elif avg_rating >= 2.5:
                    rating_description = "評價普通"
                else:
                    rating_description = "評價待改進"
        except Exception as rating_error:
            print(f"計算用戶交易評價時發生錯誤：{rating_error}")
            # 如果查詢失敗，使用預設值
            avg_rating = 0
            rating_text = "0.0"
            rating_description = "尚無評價"
        
        # 獲取用戶的評價（書評）
        evaluations_ref = db.collection("evaluations")
        reviews = []
        
        try:
            # 使用簡單查詢（只查詢 reviewer_email），然後在 Python 中排序
            # 這樣可以避免需要 Firestore 索引
            try:
                evaluations_query = evaluations_ref.where("reviewer_email", "==", view_user).limit(100)
                evaluations = evaluations_query.stream()
                
                for evaluation in evaluations:
                    eval_dict = evaluation.to_dict()
                    eval_dict["id"] = evaluation.id
                    
                    # 處理時間戳記（轉換為 UTC+8，用於排序）
                    if "created_at" in eval_dict and eval_dict["created_at"]:
                        try:
                            dt = None
                            if hasattr(eval_dict["created_at"], "strftime"):
                                dt = eval_dict["created_at"]
                            elif hasattr(eval_dict["created_at"], "timestamp"):
                                dt = eval_dict["created_at"].to_datetime()
                            
                            if dt:
                                # 轉換為 UTC+8
                                dt_utc8 = convert_to_utc8(dt)
                                created_at_str = dt_utc8.strftime("%Y-%m-%d")
                                created_at_for_sort = dt_utc8
                            else:
                                created_at_str = str(eval_dict["created_at"])[:10]
                                created_at_for_sort = eval_dict["created_at"]
                            
                            eval_dict["created_at"] = created_at_str
                            eval_dict["_created_at_for_sort"] = created_at_for_sort
                        except Exception as ts_error:
                            print(f"處理書評時間戳記時發生錯誤：{ts_error}")
                            eval_dict["created_at"] = str(eval_dict["created_at"])[:10] if eval_dict["created_at"] else ""
                            eval_dict["_created_at_for_sort"] = None
                    else:
                        eval_dict["created_at"] = ""
                        eval_dict["_created_at_for_sort"] = None
                    
                    reviews.append(eval_dict)
                
                # 按創建時間排序（降序）
                if reviews:
                    try:
                        # 使用 _created_at_for_sort 進行排序
                        reviews.sort(key=lambda x: x.get("_created_at_for_sort") if x.get("_created_at_for_sort") else "", reverse=True)
                        # 移除臨時排序欄位
                        for review in reviews:
                            if "_created_at_for_sort" in review:
                                del review["_created_at_for_sort"]
                    except Exception as sort_error:
                        print(f"排序書評時發生錯誤：{sort_error}")
                        # 如果排序失敗，嘗試按字符串排序
                        try:
                            reviews.sort(key=lambda x: x.get("created_at", ""), reverse=True)
                        except:
                            pass  # 如果排序失敗，保持原順序
                
                # 限制數量
                reviews = reviews[:50]
                print(f"找到 {len(reviews)} 個「書評」")
                
            except Exception as query_error:
                import traceback
                traceback.print_exc()
                print(f"查詢「書評」時發生錯誤：{query_error}")
                # 如果查詢失敗，reviews 保持為空列表
            
        except Exception as reviews_error:
            import traceback
            traceback.print_exc()
            print(f"查詢「書評」時發生錯誤：{reviews_error}")
            # 如果查詢失敗，reviews 保持為空列表
        
        # 獲取用戶需要的書籍（我想要書）
        wanted_books_ref = db.collection("wanted_books")
        needed_books = []
        
        try:
            # 調試輸出：顯示查詢參數
            print(f"查詢「我想要書」：requester_email == {view_user}, current_user == {current_user}")
            
            # 查詢所有該用戶的「我想要書」（不再使用 status 過濾，因為現在直接刪除）
            wanted_books_query = wanted_books_ref.where("requester_email", "==", view_user).limit(100)
            wanted_books = wanted_books_query.stream()
            
            total_count = 0
            for wanted_book in wanted_books:
                total_count += 1
                wanted_dict = wanted_book.to_dict()
                wanted_dict["id"] = wanted_book.id
                
                # 調試輸出：顯示每條記錄的資訊
                print(f"找到「我想要書」記錄：ID={wanted_book.id}, requester_email={wanted_dict.get('requester_email')}, status={wanted_dict.get('status', 'None')}, book_title={wanted_dict.get('book_title', 'None')}")
                
                # 由於現在直接從資料庫刪除，不再需要過濾 status
                # 但為了向後兼容（清理舊資料），仍然過濾掉 deleted 狀態的記錄
                status = wanted_dict.get("status")
                if status == "deleted":
                    print(f"跳過已刪除記錄（status=deleted）：{wanted_dict.get('book_title', 'Unknown')}")
                    continue
                
                # 處理時間戳記（轉換為 UTC+8，用於排序）
                if "created_at" in wanted_dict and wanted_dict["created_at"]:
                    try:
                        dt = None
                        if hasattr(wanted_dict["created_at"], "strftime"):
                            dt = wanted_dict["created_at"]
                        elif hasattr(wanted_dict["created_at"], "timestamp"):
                            dt = wanted_dict["created_at"].to_datetime()
                        
                        if dt:
                            # 轉換為 UTC+8
                            dt_utc8 = convert_to_utc8(dt)
                            created_at_str = dt_utc8.strftime("%Y-%m-%d")
                            created_at_for_sort = dt_utc8
                        else:
                            created_at_str = str(wanted_dict["created_at"])[:10]
                            created_at_for_sort = wanted_dict["created_at"]
                        
                        wanted_dict["created_at"] = created_at_str
                        wanted_dict["_created_at_for_sort"] = created_at_for_sort
                    except Exception as ts_error:
                        print(f"處理「我想要書」時間戳記時發生錯誤：{ts_error}")
                        wanted_dict["created_at"] = str(wanted_dict["created_at"])[:10] if wanted_dict["created_at"] else ""
                        wanted_dict["_created_at_for_sort"] = None
                else:
                    wanted_dict["created_at"] = ""
                    wanted_dict["_created_at_for_sort"] = None
                
                needed_books.append(wanted_dict)
            
            print(f"總共找到 {total_count} 條「我想要書」記錄，經過過濾後剩餘 {len(needed_books)} 條")
            
            # 按創建時間排序（降序）
            if needed_books:
                try:
                    # 使用 _created_at_for_sort 進行排序
                    needed_books.sort(key=lambda x: x.get("_created_at_for_sort") if x.get("_created_at_for_sort") else "", reverse=True)
                    # 移除臨時排序欄位
                    for book in needed_books:
                        if "_created_at_for_sort" in book:
                            del book["_created_at_for_sort"]
                except Exception as sort_error:
                    print(f"排序「我想要書」時發生錯誤：{sort_error}")
                    # 如果排序失敗，嘗試按字符串排序
                    try:
                        needed_books.sort(key=lambda x: x.get("created_at", ""), reverse=True)
                    except:
                        pass  # 如果排序失敗，保持原順序
            
            # 限制數量
            needed_books = needed_books[:50]
            
            # 調試輸出
            print(f"最終返回 {len(needed_books)} 個「我想要書」記錄給模板（用戶：{view_user}）")
            
        except Exception as wanted_error:
            import traceback
            traceback.print_exc()
            print(f"查詢「我想要書」時發生錯誤：{wanted_error}")
            # 如果查詢失敗，needed_books 保持為空列表
        
        return render_template("profile.html", 
                             user_display=user_display,
                             user_email=view_user,
                             user_avatar=user_avatar if 'user_avatar' in locals() else "user_cat01.png",
                             is_own_profile=is_own_profile,
                             provided_books=provided_books,
                             needed_books=needed_books,
                             reviews=reviews,
                             avg_rating=avg_rating,
                             rating_text=rating_text,
                             rating_description=rating_description)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"錯誤：{e}")
        return render_template("profile.html", 
                             user_display=session["user"].split("@")[0] if "@" in session["user"] else session["user"],
                             user_email=session["user"],
                             is_own_profile=True,
                             provided_books=[],
                             needed_books=[],
                             reviews=[],
                             avg_rating=0,
                             rating_text="0.0",
                             rating_description="尚無評價")

# 聊天室
# 私訊功能
@app.route("/message", methods=["GET"])
def message():
    if "user" not in session:
        return redirect("/login")
    
    current_user = session["user"]
    chat_id = request.args.get("chat_id", "")
    book_id = request.args.get("book_id", "")
    user_email = request.args.get("user", "")
    
    # 如果有 book_id，獲取賣家資訊
    seller_email = ""
    book_title = ""
    if book_id:
        try:
            book_ref = db.collection("books").document(book_id)
            book_doc = book_ref.get()
            if book_doc.exists:
                book_dict = book_doc.to_dict()
                seller_email = book_dict.get("seller_email", "")
                book_title = book_dict.get("title", "")
        except Exception as e:
            print(f"獲取書籍資訊時發生錯誤：{e}")
    
    # 如果有 user_email，直接使用
    if user_email and not seller_email:
        seller_email = user_email
    
    # 如果指定了 chat_id，顯示該聊天室
    if chat_id:
        try:
            chat_ref = db.collection("chats").document(chat_id)
            chat_doc = chat_ref.get()
            if chat_doc.exists:
                chat_dict = chat_doc.to_dict()
                participants = chat_dict.get("participants", [])
                # 檢查當前用戶是否為參與者
                if current_user in participants:
                    # 獲取對方資訊（處理自己與自己聊天的情況）
                    if len(participants) == 1 or (len(participants) == 2 and participants[0] == participants[1]):
                        # 自己與自己聊天
                        other_user = current_user
                    else:
                        # 正常情況：找到另一個參與者
                        other_user = participants[0] if participants[1] == current_user else participants[1]
                    
                    # 獲取對方顯示名稱和頭像
                    other_user_display = other_user.split("@")[0] if "@" in other_user else other_user
                    other_user_avatar = "user_cat01.png"
                    try:
                        user_ref = db.collection("users").document(other_user)
                        user_doc = user_ref.get()
                        if user_doc.exists:
                            user_data = user_doc.to_dict()
                            if user_data.get("display_name"):
                                other_user_display = user_data["display_name"]
                            if user_data.get("avatar"):
                                other_user_avatar = user_data["avatar"]
                    except:
                        pass
                    
                    # 獲取訊息列表並標記未讀訊息為已讀
                    messages = []
                    try:
                        messages_ref = db.collection("messages")
                        # 先嘗試使用 order_by 查詢
                        try:
                            messages_query = messages_ref.where("chat_id", "==", chat_id).order_by("created_at", direction=firestore.Query.ASCENDING).limit(100)
                            # 立即轉換為列表以觸發查詢和異常（如果索引不存在）
                            messages_docs = list(messages_query.stream())
                            print(f"使用 order_by 查詢成功，找到 {len(messages_docs)} 條訊息")
                        except Exception as order_error:
                            # 如果 order_by 失敗（可能是缺少索引），使用簡單查詢然後在內存中排序
                            print(f"使用 order_by 查詢失敗，改用簡單查詢: {order_error}")
                            messages_query = messages_ref.where("chat_id", "==", chat_id).limit(100)
                            messages_docs = list(messages_query.stream())
                            # 在內存中排序
                            all_messages = []
                            for msg_doc in messages_docs:
                                msg_dict = msg_doc.to_dict()
                                msg_dict["id"] = msg_doc.id
                                all_messages.append(msg_dict)
                            # 按 created_at 排序（使用正確的排序函數處理 Timestamp）
                            all_messages.sort(key=get_message_sort_key)
                            messages_docs = all_messages
                            print(f"使用內存排序，共 {len(all_messages)} 條訊息")
                        
                        # 標記未讀訊息為已讀（發送者不是當前用戶且未讀的訊息）
                        unread_count = 0
                        for msg_doc in messages_docs:
                            # 處理兩種情況：DocumentSnapshot 或 dict
                            if hasattr(msg_doc, 'to_dict'):
                                msg_dict = msg_doc.to_dict()
                                msg_id = msg_doc.id
                            else:
                                msg_dict = msg_doc
                                msg_id = msg_dict.get("id", "")
                            
                            sender = msg_dict.get("sender_email", "")
                            read_status = msg_dict.get("read", False)
                            
                            # 如果是別人發送的未讀訊息，標記為已讀
                            if sender != current_user and not read_status:
                                try:
                                    if hasattr(msg_doc, 'reference'):
                                        # DocumentSnapshot 情況
                                        msg_doc.reference.update({"read": True})
                                    elif msg_id:
                                        # dict 情況，需要重新獲取文檔引用
                                        msg_ref = messages_ref.document(msg_id)
                                        msg_ref.update({"read": True})
                                    unread_count += 1
                                except Exception as update_error:
                                    print(f"標記訊息為已讀時發生錯誤: {update_error}")
                        
                        if unread_count > 0:
                            print(f"已標記 {unread_count} 條訊息為已讀，chat_id={chat_id}")
                        
                        # 處理訊息
                        for msg_doc in messages_docs:
                            # 處理兩種情況：DocumentSnapshot 或 dict
                            if hasattr(msg_doc, 'to_dict'):
                                msg_dict = msg_doc.to_dict()
                                msg_dict["id"] = msg_doc.id
                            else:
                                msg_dict = msg_doc
                            
                            # 處理時間戳記（轉換為 UTC+8）
                            if "created_at" in msg_dict and msg_dict["created_at"]:
                                try:
                                    dt = None
                                    if hasattr(msg_dict["created_at"], "strftime"):
                                        dt = msg_dict["created_at"]
                                    elif hasattr(msg_dict["created_at"], "timestamp"):
                                        dt = msg_dict["created_at"].to_datetime()
                                    
                                    if dt:
                                        # 轉換為 UTC+8
                                        dt_utc8 = convert_to_utc8(dt)
                                        msg_dict["created_at"] = dt_utc8.strftime("%Y-%m-%d %H:%M")
                                    else:
                                        msg_dict["created_at"] = str(msg_dict["created_at"])[:16]
                                except Exception as time_error:
                                    print(f"處理時間戳記時發生錯誤: {time_error}")
                                    msg_dict["created_at"] = str(msg_dict["created_at"])[:16] if msg_dict["created_at"] else ""
                            else:
                                msg_dict["created_at"] = ""
                            
                            messages.append(msg_dict)
                        
                        print(f"成功獲取 {len(messages)} 條訊息，chat_id={chat_id}")
                    except Exception as e:
                        import traceback
                        print(f"獲取訊息時發生錯誤：{e}")
                        traceback.print_exc()
                    
                    # 判斷當前用戶是否是賣家（通過 book_id 或交易提醒中的 book_id）
                    is_seller = False
                    transaction_book_id = book_id
                    transaction_reminder = None
                    try:
                        reminders_ref = db.collection("transaction_reminders")
                        reminders_query = reminders_ref.where("chat_id", "==", chat_id).where("completed", "==", False).limit(1)
                        reminders = list(reminders_query.stream())
                        if reminders:
                            reminder_dict = reminders[0].to_dict()
                            reminder_dict["id"] = reminders[0].id
                            transaction_book_id = reminder_dict.get("book_id", book_id)
                            # 處理時間戳記（轉換為 UTC+8）
                            if "transaction_datetime" in reminder_dict and reminder_dict["transaction_datetime"]:
                                try:
                                    dt = None
                                    if hasattr(reminder_dict["transaction_datetime"], "strftime"):
                                        dt = reminder_dict["transaction_datetime"]
                                    elif hasattr(reminder_dict["transaction_datetime"], "timestamp"):
                                        dt = reminder_dict["transaction_datetime"].to_datetime()
                                    if dt:
                                        dt_utc8 = convert_to_utc8(dt)
                                        reminder_dict["transaction_datetime"] = dt_utc8.isoformat()
                                except Exception as time_error:
                                    print(f"處理交易提醒時間戳記時發生錯誤: {time_error}")
                            transaction_reminder = reminder_dict
                    except Exception as reminder_error:
                        print(f"獲取交易提醒時發生錯誤: {reminder_error}")
                    
                    # 檢查當前用戶是否是賣家（根據交易提醒的 created_by）
                    is_seller = False
                    if transaction_reminder:
                        # 如果交易提醒存在，根據 created_by 判斷
                        is_seller = (transaction_reminder.get("created_by", "") == current_user)
                    elif transaction_book_id:
                        # 如果沒有交易提醒，根據書籍的 seller_email 判斷
                        try:
                            book_ref = db.collection("books").document(transaction_book_id)
                            book_doc = book_ref.get()
                            if book_doc.exists:
                                book_dict = book_doc.to_dict()
                                is_seller = (book_dict.get("seller_email", "") == current_user)
                        except Exception as book_check_error:
                            print(f"檢查賣家身份時發生錯誤: {book_check_error}")
                    
                    # 獲取交易評價狀態（如果交易已完成）
                    transaction_evaluation_status = None
                    if transaction_reminder and transaction_reminder.get("completed"):
                        try:
                            evaluations_ref = db.collection("transaction_evaluations")
                            # 查詢當前用戶對對方的評價
                            eval_query = evaluations_ref.where("transaction_id", "==", transaction_reminder["id"])\
                                                       .where("evaluator_email", "==", current_user).limit(1)
                            eval_docs = list(eval_query.stream())
                            transaction_evaluation_status = {
                                "has_evaluated": len(eval_docs) > 0,
                                "evaluation_id": eval_docs[0].id if eval_docs else None
                            }
                        except Exception as eval_error:
                            print(f"獲取評價狀態時發生錯誤: {eval_error}")
                    
                    # 如果有 book_id，傳遞給模板用於顯示上下文
                    return render_template("message.html",
                                         chat_id=chat_id,
                                         other_user=other_user,
                                         other_user_display=other_user_display,
                                         other_user_avatar=other_user_avatar,
                                         messages=messages,
                                         book_id=book_id if book_id else "",
                                         book_title=book_title if book_title else "",
                                         transaction_reminder=transaction_reminder,
                                         is_seller=is_seller,
                                         transaction_evaluation_status=transaction_evaluation_status)
        except Exception as e:
            print(f"獲取聊天室時發生錯誤：{e}")
            return redirect("/message")
    
    # 如果有 seller_email，創建或獲取聊天室（允許自己與自己聊天）
    if seller_email:
        try:
            # 創建排序後的參與者列表（確保唯一性）
            # 如果是自己與自己聊天，participants 包含兩個相同的元素
            if seller_email == current_user:
                participants = [current_user, current_user]
            else:
                participants = sorted([current_user, seller_email])
            participants_key = "_".join(participants)
            
            # 查找是否已存在聊天室
            chats_ref = db.collection("chats")
            existing_chats = chats_ref.where("participants", "==", participants).limit(1).stream()
            existing_chat = list(existing_chats)
            
            if existing_chat:
                # 使用現有聊天室
                chat_id = existing_chat[0].id
                chat_dict = existing_chat[0].to_dict()
            else:
                # 創建新聊天室（基於參與者，不基於書籍）
                chat_data = {
                    "participants": participants,
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "last_message": "",
                    "last_message_time": firestore.SERVER_TIMESTAMP,
                    "last_message_sender": ""
                }
                chat_ref = db.collection("chats").document()
                chat_ref.set(chat_data)
                chat_id = chat_ref.id
                chat_dict = chat_data
                print(f"創建新聊天室: chat_id={chat_id}, participants={participants}")
            
            # 獲取對方資訊
            other_user = seller_email
            other_user_display = other_user.split("@")[0] if "@" in other_user else other_user
            other_user_avatar = "user_cat01.png"
            try:
                user_ref = db.collection("users").document(other_user)
                user_doc = user_ref.get()
                if user_doc.exists:
                    user_data = user_doc.to_dict()
                    if user_data.get("display_name"):
                        other_user_display = user_data["display_name"]
                    if user_data.get("avatar"):
                        other_user_avatar = user_data["avatar"]
            except:
                pass
            
            # 獲取訊息列表並標記未讀訊息為已讀
            messages = []
            try:
                messages_ref = db.collection("messages")
                # 先嘗試使用 order_by 查詢
                try:
                    messages_query = messages_ref.where("chat_id", "==", chat_id).order_by("created_at", direction=firestore.Query.ASCENDING).limit(100)
                    # 立即轉換為列表以觸發查詢和異常（如果索引不存在）
                    messages_docs = list(messages_query.stream())
                    print(f"使用 order_by 查詢成功，找到 {len(messages_docs)} 條訊息")
                except Exception as order_error:
                    # 如果 order_by 失敗（可能是缺少索引），使用簡單查詢然後在內存中排序
                    print(f"使用 order_by 查詢失敗，改用簡單查詢: {order_error}")
                    messages_query = messages_ref.where("chat_id", "==", chat_id).limit(100)
                    messages_docs = list(messages_query.stream())
                    # 在內存中排序
                    all_messages = []
                    for msg_doc in messages_docs:
                        msg_dict = msg_doc.to_dict()
                        msg_dict["id"] = msg_doc.id
                        all_messages.append(msg_dict)
                    # 按 created_at 排序（使用正確的排序函數處理 Timestamp）
                    all_messages.sort(key=get_message_sort_key)
                    messages_docs = all_messages
                    print(f"使用內存排序，共 {len(all_messages)} 條訊息")
                
                # 標記未讀訊息為已讀（發送者不是當前用戶且未讀的訊息）
                unread_count = 0
                for msg_doc in messages_docs:
                    # 處理兩種情況：DocumentSnapshot 或 dict
                    if hasattr(msg_doc, 'to_dict'):
                        msg_dict = msg_doc.to_dict()
                        msg_id = msg_doc.id
                    else:
                        msg_dict = msg_doc
                        msg_id = msg_dict.get("id", "")
                    
                    sender = msg_dict.get("sender_email", "")
                    read_status = msg_dict.get("read", False)
                    
                    # 如果是別人發送的未讀訊息，標記為已讀
                    if sender != current_user and not read_status:
                        try:
                            if hasattr(msg_doc, 'reference'):
                                # DocumentSnapshot 情況
                                msg_doc.reference.update({"read": True})
                            elif msg_id:
                                # dict 情況，需要重新獲取文檔引用
                                msg_ref = messages_ref.document(msg_id)
                                msg_ref.update({"read": True})
                            unread_count += 1
                        except Exception as update_error:
                            print(f"標記訊息為已讀時發生錯誤: {update_error}")
                
                if unread_count > 0:
                    print(f"已標記 {unread_count} 條訊息為已讀，chat_id={chat_id}")
                
                # 處理訊息
                for msg_doc in messages_docs:
                    # 處理兩種情況：DocumentSnapshot 或 dict
                    if hasattr(msg_doc, 'to_dict'):
                        msg_dict = msg_doc.to_dict()
                        msg_dict["id"] = msg_doc.id
                    else:
                        msg_dict = msg_doc
                    
                    # 處理時間戳記（轉換為 UTC+8）
                    if "created_at" in msg_dict and msg_dict["created_at"]:
                        try:
                            dt = None
                            if hasattr(msg_dict["created_at"], "strftime"):
                                dt = msg_dict["created_at"]
                            elif hasattr(msg_dict["created_at"], "timestamp"):
                                dt = msg_dict["created_at"].to_datetime()
                            
                            if dt:
                                # 轉換為 UTC+8
                                dt_utc8 = convert_to_utc8(dt)
                                msg_dict["created_at"] = dt_utc8.strftime("%Y-%m-%d %H:%M")
                            else:
                                msg_dict["created_at"] = str(msg_dict["created_at"])[:16]
                        except Exception as time_error:
                            print(f"處理時間戳記時發生錯誤: {time_error}")
                            msg_dict["created_at"] = str(msg_dict["created_at"])[:16] if msg_dict["created_at"] else ""
                    else:
                        msg_dict["created_at"] = ""
                    
                    messages.append(msg_dict)
                
                print(f"成功獲取 {len(messages)} 條訊息，chat_id={chat_id}")
            except Exception as e:
                import traceback
                print(f"獲取訊息時發生錯誤：{e}")
                traceback.print_exc()
            
            # 獲取交易提醒（如果有的話，包括已完成的）
            transaction_reminder = None
            try:
                reminders_ref = db.collection("transaction_reminders")
                # 先查詢未完成的交易提醒
                reminders_query = reminders_ref.where("chat_id", "==", chat_id).where("completed", "==", False).limit(1)
                reminders = list(reminders_query.stream())
                # 如果沒有未完成的，查詢已完成的（用於顯示評價提示）
                if not reminders:
                    completed_query = reminders_ref.where("chat_id", "==", chat_id).where("completed", "==", True).order_by("completed_at", direction=firestore.Query.DESCENDING).limit(1)
                    try:
                        reminders = list(completed_query.stream())
                    except Exception as order_error:
                        # 如果 order_by 失敗，使用簡單查詢
                        completed_query = reminders_ref.where("chat_id", "==", chat_id).where("completed", "==", True).limit(1)
                        reminders = list(completed_query.stream())
                        # 在內存中按 completed_at 排序
                        if reminders:
                            def get_reminder_sort_key(reminder_doc):
                                reminder_dict = reminder_doc.to_dict()
                                completed_at = reminder_dict.get("completed_at")
                                if not completed_at:
                                    return datetime.min
                                if hasattr(completed_at, "strftime"):
                                    return completed_at
                                elif hasattr(completed_at, "timestamp"):
                                    try:
                                        return completed_at.to_datetime()
                                    except:
                                        return datetime.min
                                else:
                                    return datetime.min
                            reminders.sort(key=get_reminder_sort_key, reverse=True)
                            reminders = reminders[:1]  # 只取最新的一個
                
                if reminders:
                    reminder_dict = reminders[0].to_dict()
                    reminder_dict["id"] = reminders[0].id
                    # 處理時間戳記（轉換為 UTC+8）
                    if "transaction_datetime" in reminder_dict and reminder_dict["transaction_datetime"]:
                        try:
                            dt = None
                            if hasattr(reminder_dict["transaction_datetime"], "strftime"):
                                dt = reminder_dict["transaction_datetime"]
                            elif hasattr(reminder_dict["transaction_datetime"], "timestamp"):
                                dt = reminder_dict["transaction_datetime"].to_datetime()
                            if dt:
                                dt_utc8 = convert_to_utc8(dt)
                                reminder_dict["transaction_datetime"] = dt_utc8.isoformat()
                        except Exception as time_error:
                            print(f"處理交易提醒時間戳記時發生錯誤: {time_error}")
                    transaction_reminder = reminder_dict
            except Exception as reminder_error:
                print(f"獲取交易提醒時發生錯誤: {reminder_error}")
            
            # 如果有 book_id，傳遞給模板用於顯示上下文
            return render_template("message.html",
                                 chat_id=chat_id,
                                 other_user=other_user,
                                 other_user_display=other_user_display,
                                 other_user_avatar=other_user_avatar,
                                 messages=messages,
                                 book_id=book_id if book_id else "",
                                 book_title=book_title if book_title else "",
                                 transaction_reminder=transaction_reminder)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"創建聊天室時發生錯誤：{e}")
            return redirect("/")
    
    # 顯示聊天列表
    try:
        # 獲取當前用戶的所有聊天室
        chats_ref = db.collection("chats")
        # 查詢包含當前用戶的聊天室
        try:
            chats_query = chats_ref.where("participants", "array_contains", current_user).order_by("last_message_time", direction=firestore.Query.DESCENDING).limit(50)
            chats = list(chats_query.stream())
            print(f"使用 order_by 查詢聊天室成功，找到 {len(chats)} 個聊天室")
        except Exception as order_error:
            # 如果 order_by 失敗，使用簡單查詢然後在內存中排序
            print(f"使用 order_by 查詢聊天室失敗，改用簡單查詢: {order_error}")
            chats_query = chats_ref.where("participants", "array_contains", current_user).limit(50)
            chats = list(chats_query.stream())
            # 在內存中按 last_message_time 排序
            def get_chat_sort_key(chat_doc):
                chat_dict = chat_doc.to_dict()
                last_time = chat_dict.get("last_message_time")
                if not last_time:
                    return datetime.min
                if hasattr(last_time, "to_datetime"):
                    try:
                        return last_time.to_datetime()
                    except:
                        return datetime.min
                elif hasattr(last_time, "timestamp"):
                    try:
                        return datetime.fromtimestamp(last_time.timestamp())
                    except:
                        return datetime.min
                elif hasattr(last_time, "strftime"):
                    return last_time
                else:
                    return datetime.min
            chats.sort(key=get_chat_sort_key, reverse=True)
            print(f"使用內存排序聊天室，共 {len(chats)} 個聊天室")
        
        chat_list = []
        for chat_doc in chats:
            chat_dict = chat_doc.to_dict()
            chat_dict["id"] = chat_doc.id
            
            # 獲取對方資訊（處理自己與自己聊天的情況）
            participants = chat_dict.get("participants", [])
            if len(participants) == 1 or (len(participants) == 2 and participants[0] == participants[1]):
                # 自己與自己聊天
                other_user = current_user
            else:
                # 正常情況：找到另一個參與者
                other_user = participants[0] if participants[1] == current_user else participants[1]
            
            other_user_display = other_user.split("@")[0] if "@" in other_user else other_user
            other_user_avatar = "user_cat01.png"
            try:
                user_ref = db.collection("users").document(other_user)
                user_doc = user_ref.get()
                if user_doc.exists:
                    user_data = user_doc.to_dict()
                    if user_data.get("display_name"):
                        other_user_display = user_data["display_name"]
                    if user_data.get("avatar"):
                        other_user_avatar = user_data["avatar"]
            except:
                pass
            
            # 處理時間戳記（轉換為 UTC+8）
            last_message_time_str = ""
            if "last_message_time" in chat_dict and chat_dict["last_message_time"]:
                try:
                    dt = None
                    if hasattr(chat_dict["last_message_time"], "strftime"):
                        dt = chat_dict["last_message_time"]
                    elif hasattr(chat_dict["last_message_time"], "timestamp"):
                        dt = chat_dict["last_message_time"].to_datetime()
                    
                    if dt:
                        # 轉換為 UTC+8
                        dt_utc8 = convert_to_utc8(dt)
                        last_message_time_str = dt_utc8.strftime("%Y-%m-%d %H:%M")
                    else:
                        last_message_time_str = str(chat_dict["last_message_time"])[:16]
                except:
                    last_message_time_str = str(chat_dict["last_message_time"])[:16] if chat_dict["last_message_time"] else ""
            
            # 獲取最新一則訊息和未讀訊息數量
            last_message_content = chat_dict.get("last_message", "")
            unread_count = 0
            recent_book_title = ""
            
            try:
                messages_ref = db.collection("messages")
                # 獲取該聊天室的所有訊息
                all_messages_query = messages_ref.where("chat_id", "==", chat_dict["id"]).limit(100)
                all_messages = list(all_messages_query.stream())
                
                if all_messages:
                    # 按時間排序獲取最新訊息
                    all_messages_dicts = []
                    for msg_doc in all_messages:
                        msg_dict = msg_doc.to_dict()
                        msg_dict["id"] = msg_doc.id
                        all_messages_dicts.append(msg_dict)
                    all_messages_dicts.sort(key=get_message_sort_key, reverse=True)
                    
                    # 獲取最新訊息
                    latest_message = all_messages_dicts[0] if all_messages_dicts else None
                    if latest_message:
                        last_message_content = latest_message.get("content", "")
                        recent_book_title = latest_message.get("book_title", "")
                    
                    # 計算未讀訊息數量（發送者不是當前用戶且未讀）
                    for msg_dict in all_messages_dicts:
                        sender = msg_dict.get("sender_email", "")
                        read_status = msg_dict.get("read", False)
                        if sender != current_user and not read_status:
                            unread_count += 1
            except Exception as msg_error:
                print(f"獲取聊天室訊息時發生錯誤: {msg_error}")
                # 如果獲取訊息失敗，使用聊天室中的 last_message
                last_message_content = chat_dict.get("last_message", "")
            
            chat_list.append({
                "id": chat_dict["id"],
                "other_user": other_user,
                "other_user_display": other_user_display,
                "other_user_avatar": other_user_avatar,
                "last_message": last_message_content,
                "last_message_time": last_message_time_str,
                "recent_book_title": recent_book_title,
                "unread_count": unread_count
            })
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"獲取聊天列表時發生錯誤：{e}")
        chat_list = []
    
    return render_template("message.html", chat_list=chat_list)

# 設定
@app.route("/setting", methods=["GET", "POST"])
def setting():
    if "user" not in session:
        return redirect("/login")  # 未登入則跳轉到登入頁
    return render_template("setting.html")  # 渲染設定頁面

# 編輯個人資訊
@app.route("/edit_profile", methods=["GET", "POST"])
def edit_profile():
    if "user" not in session:
        return redirect("/login")
    
    current_user = session["user"]
    
    if request.method == "POST":
        try:
            # 獲取表單資料
            display_name = request.form.get("display_name", "").strip()
            avatar = request.form.get("avatar", "user_cat01.png").strip()
            
            # 驗證頭像選項
            valid_avatars = ["user_cat01.png", "user_cat02.png", "user_female.png", "user_male.png"]
            if avatar not in valid_avatars:
                avatar = "user_cat01.png"
            
            if not display_name:
                # 如果沒有輸入顯示名稱，使用 email 前綴
                if "@" in current_user:
                    display_name = current_user.split("@")[0]
                else:
                    display_name = current_user
            
            # 更新或創建用戶資料到 Firestore
            user_ref = db.collection("users").document(current_user)
            user_doc = user_ref.get()
            
            if user_doc.exists:
                # 更新現有用戶資料
                user_ref.update({
                    "display_name": display_name,
                    "avatar": avatar,
                    "updated_at": firestore.SERVER_TIMESTAMP
                })
                print(f"更新用戶資料：{current_user}, display_name={display_name}, avatar={avatar}")
            else:
                # 創建新用戶資料
                user_ref.set({
                    "email": current_user,
                    "display_name": display_name,
                    "avatar": avatar,
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "updated_at": firestore.SERVER_TIMESTAMP
                })
                print(f"創建用戶資料：{current_user}, display_name={display_name}, avatar={avatar}")
            
            return redirect("/profile?success=profile_updated")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"更新個人資料時發生錯誤：{e}")
            return render_template("edit_profile.html", 
                                 user_display=display_name if 'display_name' in locals() else (current_user.split("@")[0] if "@" in current_user else current_user), 
                                 user_email=current_user,
                                 error=f"更新失敗：{str(e)}")
    
    # GET 請求：獲取當前用戶資訊
    try:
        # 嘗試從 Firestore 讀取用戶資料
        user_ref = db.collection("users").document(current_user)
        user_doc = user_ref.get()
        
        if user_doc.exists:
            user_data = user_doc.to_dict()
            user_display = user_data.get("display_name", "")
            user_avatar = user_data.get("avatar", "user_cat01.png")
            if not user_display:
                # 如果沒有 display_name，使用 email 前綴
                if "@" in current_user:
                    user_display = current_user.split("@")[0]
                else:
                    user_display = current_user
        else:
            # 如果用戶資料不存在，使用 email 前綴和預設頭像
            if "@" in current_user:
                user_display = current_user.split("@")[0]
            else:
                user_display = current_user
            user_avatar = "user_cat01.png"
    except Exception as e:
        print(f"讀取用戶資料時發生錯誤：{e}")
        # 如果讀取失敗，使用 email 前綴和預設頭像
        if "@" in current_user:
            user_display = current_user.split("@")[0]
        else:
            user_display = current_user
        user_avatar = "user_cat01.png"
    
    return render_template("edit_profile.html", 
                         user_display=user_display, 
                         user_email=current_user,
                         user_avatar=user_avatar if 'user_avatar' in locals() else "user_cat01.png")

# 將 Firebase 錯誤訊息轉換為用戶友好的中文提示
def get_friendly_error_message(error_msg):
    """將技術錯誤訊息轉換為用戶友好的中文提示"""
    error_msg_lower = error_msg.lower()
    
    # 密碼相關錯誤
    if "invalid_password" in error_msg_lower or "wrong-password" in error_msg_lower:
        return "目前密碼錯誤，請重新輸入。"
    if "weak_password" in error_msg_lower:
        return "新密碼強度不足，請使用更強的密碼。"
    if "password" in error_msg_lower and "too short" in error_msg_lower:
        return "密碼長度不足，請至少使用 6 個字元。"
    
    # 認證相關錯誤
    if "invalid_id_token" in error_msg_lower or "invalid_token" in error_msg_lower:
        return "認證已過期，請重新登入後再試。"
    if "user_not_found" in error_msg_lower or "user-disabled" in error_msg_lower:
        return "找不到用戶或帳號已被停用，請聯繫管理員。"
    if "email_not_verified" in error_msg_lower:
        return "電子郵件尚未驗證，請先驗證您的電子郵件。"
    
    # 網路相關錯誤
    if "network" in error_msg_lower or "connection" in error_msg_lower:
        return "網路連線錯誤，請檢查您的網路連線後再試。"
    if "timeout" in error_msg_lower:
        return "連線逾時，請稍後再試。"
    
    # 請求相關錯誤
    if "too_many_requests" in error_msg_lower or "quota" in error_msg_lower:
        return "請求過於頻繁，請稍後再試。"
    if "invalid_request" in error_msg_lower:
        return "請求無效，請確認輸入的資料是否正確。"
    
    # 權限相關錯誤
    if "permission" in error_msg_lower or "unauthorized" in error_msg_lower:
        return "沒有權限執行此操作，請確認您已正確登入。"
    
    # 通用錯誤
    if "internal_error" in error_msg_lower or "server_error" in error_msg_lower:
        return "伺服器發生錯誤，請稍後再試。"
    
    # 如果無法識別錯誤類型，返回通用提示
    return "修改密碼時發生錯誤，請確認目前密碼是否正確，或稍後再試。"

# 修改密碼
@app.route("/change_password", methods=["GET", "POST"])
def change_password():
    if "user" not in session:
        return redirect("/login")
    
    if request.method == "POST":
        try:
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")
            
            if not current_password or not new_password or not confirm_password:
                return render_template("change_password.html", error="請填寫所有欄位。")
            
            if new_password != confirm_password:
                return render_template("change_password.html", error="新密碼與確認密碼不一致，請重新輸入。")
            
            # 驗證新舊密碼是否相同
            if current_password == new_password:
                return render_template("change_password.html", error="新密碼與目前密碼相同，請使用不同的密碼。")
            
            # 驗證新密碼是否符合規則
            password_errors = []
            if len(new_password) < 6:
                password_errors.append("密碼長度至少6位")
            if not any(c.isupper() for c in new_password):
                password_errors.append("至少包含一個大寫字母")
            if not any(c.islower() for c in new_password):
                password_errors.append("至少包含一個小寫字母")
            
            if password_errors:
                return render_template("change_password.html", error="新密碼不符合規則：" + "，".join(password_errors))
            
            # 使用 Firebase Auth 修改密碼
            current_user = session["user"]
            try:
                # 先重新登入以獲取 token
                user = auth_firebase.sign_in_with_email_and_password(current_user, current_password)
                
                # 使用 Firebase REST API 更新密碼
                update_url = f"https://identitytoolkit.googleapis.com/v1/accounts:update?key={firebase_api_key}"
                update_data = {
                    "idToken": user['idToken'],
                    "password": new_password,
                    "returnSecureToken": True
                }
                
                response = requests.post(update_url, json=update_data)
                if response.status_code == 200:
                    # 修改成功，重定向到修改密碼頁面並顯示成功訊息
                    return redirect("/change_password?success=password_changed")
                else:
                    # 處理 Firebase REST API 錯誤
                    try:
                        error_data = response.json()
                        error_msg = error_data.get('error', {}).get('message', '')
                        friendly_error = get_friendly_error_message(error_msg)
                        return render_template("change_password.html", error=friendly_error)
                    except:
                        return render_template("change_password.html", error="修改密碼失敗，請確認目前密碼是否正確，或稍後再試。")
            except Exception as e:
                # 處理登入錯誤
                error_msg = str(e)
                friendly_error = get_friendly_error_message(error_msg)
                
                # 如果是常見的登入錯誤，提供更明確的提示
                if "INVALID_PASSWORD" in error_msg.upper() or "wrong-password" in error_msg.lower():
                    return render_template("change_password.html", error="目前密碼錯誤，請重新輸入。")
                elif "INVALID_EMAIL" in error_msg.upper() or "email-not-found" in error_msg.lower():
                    return render_template("change_password.html", error="找不到此帳號，請確認帳號是否正確。")
                elif "too-many-requests" in error_msg.lower():
                    return render_template("change_password.html", error="嘗試次數過多，請稍後再試。")
                else:
                    return render_template("change_password.html", error=friendly_error)
        except Exception as e:
            # 處理其他未預期的錯誤
            import traceback
            traceback.print_exc()
            error_msg = str(e)
            friendly_error = get_friendly_error_message(error_msg)
            return render_template("change_password.html", error=friendly_error)
    
    return render_template("change_password.html")

# 刪除帳號
@app.route("/delete_account", methods=["POST"])
def delete_account():
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        data = request.json
        if not data.get("confirm"):
            return jsonify({"success": False, "error": "需要確認"}), 400
        
        current_user = session["user"]
        
        # 刪除用戶在 Firestore 中的資料
        # 1. 刪除用戶的書籍
        books_ref = db.collection("books")
        books_query = books_ref.where("seller_email", "==", current_user)
        books = books_query.stream()
        for book in books:
            book.reference.delete()
        
        # 2. 刪除用戶的評價
        evaluations_ref = db.collection("evaluations")
        evaluations_query = evaluations_ref.where("reviewer_email", "==", current_user)
        evaluations = evaluations_query.stream()
        for evaluation in evaluations:
            evaluation.reference.delete()
        
        # 3. 刪除 Firebase Auth 中的用戶
        # 注意：這需要管理員權限，可能需要使用 Firebase Admin SDK
        # 目前先標記為已刪除，實際刪除需要額外處理
        print(f"用戶 {current_user} 請求刪除帳號")
        
        # 清除 session
        session.pop("user", None)
        
        return jsonify({"success": True, "message": "帳號已刪除"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

# 個人收藏
@app.route("/collects", methods=["GET", "POST"])
def collects():
    if "user" not in session:
        return redirect("/login")  # 未登入則跳轉到登入頁
    
    try:
        current_user = session["user"]
        favorites_ref = db.collection("favorites")
        
        # 查詢所有收藏（向後兼容：舊的收藏記錄可能沒有 item_type，預設為 "book"）
        favorites_query = favorites_ref.where("user_email", "==", current_user).limit(100)
        favorites = favorites_query.stream()
        
        favorite_books = []
        favorite_wanted_books = []
        
        for favorite in favorites:
            fav_dict = favorite.to_dict()
            item_id = fav_dict.get("item_id") or fav_dict.get("book_id")  # 向後兼容：舊記錄使用 book_id
            item_type = fav_dict.get("item_type", "book")  # 預設為 "book" 以向後兼容
            created_at = fav_dict.get("created_at")
            
            if not item_id:
                continue  # 跳過無效的收藏記錄
            
            # 處理時間戳記
            if created_at:
                try:
                    if hasattr(created_at, "strftime"):
                        created_at_str = created_at.strftime("%Y-%m-%d")
                    elif hasattr(created_at, "timestamp"):
                        dt = created_at.to_datetime()
                        created_at_str = dt.strftime("%Y-%m-%d")
                    else:
                        created_at_str = str(created_at)[:10]
                except:
                    created_at_str = str(created_at)[:10] if created_at else ""
            else:
                created_at_str = ""
            
            if item_type == "wanted_book":
                # 獲取換書資訊
                wanted_book_ref = db.collection("wanted_books").document(item_id)
                wanted_book_doc = wanted_book_ref.get()
                if wanted_book_doc.exists:
                    wanted_book_dict = wanted_book_doc.to_dict()
                    wanted_book_dict["id"] = item_id
                    wanted_book_dict["favorite_id"] = favorite.id
                    wanted_book_dict["favorite_created_at"] = created_at_str
                    favorite_wanted_books.append(wanted_book_dict)
            else:
                # 獲取書籍資訊（預設或舊的收藏記錄）
                book_ref = db.collection("books").document(item_id)
                book_doc = book_ref.get()
                if book_doc.exists:
                    book_dict = book_doc.to_dict()
                    book_dict["id"] = item_id
                    book_dict["favorite_id"] = favorite.id
                    book_dict["favorite_created_at"] = created_at_str
                    # 處理圖片
                    if not book_dict.get("front_image") or book_dict.get("front_image", "").startswith("static/"):
                        book_dict["front_image"] = "/static/images/book_original.png"
                    # 處理評價資訊
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
                    favorite_books.append(book_dict)
        
        return render_template("collects.html", 
                             favorite_books=favorite_books,
                             favorite_wanted_books=favorite_wanted_books)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return render_template("collects.html", 
                             favorite_books=[],
                             favorite_wanted_books=[])

# 書籍詳情
@app.route("/book/<book_id>", methods=["GET"])
def book_detail(book_id):
    if "user" not in session:
        return redirect("/login")
    
    try:
        # 驗證 book_id
        if not book_id or book_id.strip() == "":
            print(f"錯誤：book_id 為空")
            return redirect("/?error=book_not_found")
        
        print(f"嘗試獲取書籍詳情：book_id={book_id}")
        
        # 獲取書籍資料
        book_ref = db.collection("books").document(book_id)
        book_doc = book_ref.get()
        
        if not book_doc.exists:
            print(f"錯誤：書籍不存在，book_id={book_id}")
            return redirect("/?error=book_not_found")
        
        book_dict = book_doc.to_dict()
        if not book_dict:
            print(f"錯誤：書籍資料為空，book_id={book_id}")
            return redirect("/?error=book_not_found")
        
        book_dict["id"] = book_doc.id
        
        # 處理圖片
        if not book_dict.get("front_image"):
            book_dict["front_image"] = "static/images/book_original.png"
        if not book_dict.get("back_image"):
            book_dict["back_image"] = "static/images/book_original.png"
        
        # 處理賣家電子郵件顯示
        seller_email = book_dict.get("seller_email", "")
        if seller_email:
            if "@" in seller_email:
                book_dict["seller_display"] = seller_email.split("@")[0]
            else:
                book_dict["seller_display"] = seller_email
        else:
            book_dict["seller_display"] = "未知"
        
        # 獲取該書籍的所有評價（書評）
        reviews = []
        ratings = []
        evaluations_ref = db.collection("evaluations")
        
        # 方法1：優先使用書籍的 evaluation_id（如果存在）
        evaluation_id = book_dict.get("evaluation_id", "")
        if evaluation_id:
            try:
                eval_ref = evaluations_ref.document(evaluation_id)
                eval_doc = eval_ref.get()
                if eval_doc.exists:
                    eval_dict = eval_doc.to_dict()
                    eval_dict["id"] = eval_doc.id
                    
                    # 處理時間戳記（轉換為 UTC+8）
                    if "created_at" in eval_dict and eval_dict["created_at"]:
                        try:
                            dt = None
                            if hasattr(eval_dict["created_at"], "strftime"):
                                dt = eval_dict["created_at"]
                            elif hasattr(eval_dict["created_at"], "timestamp"):
                                dt = eval_dict["created_at"].to_datetime()
                            
                            if dt:
                                # 轉換為 UTC+8
                                dt_utc8 = convert_to_utc8(dt)
                                eval_dict["created_at"] = dt_utc8.strftime("%Y-%m-%d")
                            else:
                                eval_dict["created_at"] = str(eval_dict["created_at"])[:10]
                        except Exception as e:
                            print(f"處理時間戳記時發生錯誤：{e}")
                            eval_dict["created_at"] = str(eval_dict["created_at"])[:10] if eval_dict["created_at"] else ""
                    
                    reviews.append(eval_dict)
                    rating = eval_dict.get("rating", 0)
                    if rating > 0:
                        ratings.append(rating)
                    print(f"從 evaluation_id 找到評價：{evaluation_id}")
            except Exception as e:
                print(f"讀取 evaluation_id 評價時發生錯誤：{e}")
        
        # 方法2：根據書名查找所有相關評價（補充評價列表）
        try:
            book_title = book_dict.get("title", "")
            if book_title:
                try:
                    # 根據書名查找所有相關評價
                    evaluations_query = evaluations_ref.where("book_title", "==", book_title).order_by("created_at", direction=firestore.Query.DESCENDING).limit(50)
                    evaluations = evaluations_query.stream()
                except Exception as query_error:
                    # 如果排序失敗，使用簡單查詢
                    print(f"評價查詢排序失敗，使用簡單查詢：{query_error}")
                    evaluations_query = evaluations_ref.where("book_title", "==", book_title).limit(50)
                    evaluations = evaluations_query.stream()
                
                # 記錄已添加的評價 ID，避免重複
                added_eval_ids = {review.get("id") for review in reviews}
                
                for evaluation in evaluations:
                    try:
                        eval_id = evaluation.id
                        # 如果已經從 evaluation_id 添加過，跳過
                        if eval_id in added_eval_ids:
                            continue
                            
                        eval_dict = evaluation.to_dict()
                        eval_dict["id"] = eval_id
                        
                        # 收集評分用於計算平均評分
                        rating = eval_dict.get("rating", 0)
                        if rating > 0:
                            ratings.append(rating)
                        
                        # 處理時間戳記（轉換為 UTC+8）
                        if "created_at" in eval_dict and eval_dict["created_at"]:
                            try:
                                dt = None
                                if hasattr(eval_dict["created_at"], "strftime"):
                                    dt = eval_dict["created_at"]
                                elif hasattr(eval_dict["created_at"], "timestamp"):
                                    dt = eval_dict["created_at"].to_datetime()
                                
                                if dt:
                                    # 轉換為 UTC+8
                                    dt_utc8 = convert_to_utc8(dt)
                                    eval_dict["created_at"] = dt_utc8.strftime("%Y-%m-%d")
                                else:
                                    eval_dict["created_at"] = str(eval_dict["created_at"])[:10]
                            except Exception as e:
                                print(f"處理時間戳記時發生錯誤：{e}")
                                eval_dict["created_at"] = str(eval_dict["created_at"])[:10] if eval_dict["created_at"] else ""
                        
                        reviews.append(eval_dict)
                        added_eval_ids.add(eval_id)
                    except Exception as eval_error:
                        print(f"處理評價時發生錯誤：{eval_error}")
                        continue
        except Exception as reviews_error:
            print(f"查詢評價時發生錯誤：{reviews_error}")
            # 評價查詢失敗不影響書籍詳情顯示，繼續執行
        
        # 計算平均評分
        if ratings:
            avg_rating = sum(ratings) / len(ratings)
            book_dict["rating"] = avg_rating
        else:
            book_dict["rating"] = 0
        
        # 檢查是否為教科書並收集課程資訊
        is_textbook = False
        course_info_list = []
        
        print(f"找到 {len(reviews)} 個評價")
        for review in reviews:
            book_type = review.get("book_type", "")
            print(f"評價 ID: {review.get('id')}, book_type: {book_type}")
            
            if book_type == "course":
                is_textbook = True
                course_name = review.get("course_name", "")
                instructor = review.get("instructor", "")
                if course_name or instructor:
                    # 避免重複的課程資訊
                    course_info = {
                        "course_name": course_name,
                        "instructor": instructor
                    }
                    # 檢查是否已存在相同的課程資訊
                    course_info_str = f"{course_name}|{instructor}"
                    existing_strs = [f"{ci['course_name']}|{ci['instructor']}" for ci in course_info_list]
                    if course_info_str not in existing_strs:
                        course_info_list.append(course_info)
                        print(f"添加課程資訊：{course_name} - {instructor}")
        
        book_dict["is_textbook"] = is_textbook
        book_dict["course_info_list"] = course_info_list
        print(f"書籍是否為教科書：{is_textbook}，課程數量：{len(course_info_list)}")
        
        print(f"成功獲取書籍詳情：book_id={book_id}, title={book_dict.get('title', 'Unknown')}, is_textbook={is_textbook}")
        return render_template("book_detail.html", book=book_dict, reviews=reviews)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"書籍詳情頁面發生錯誤：book_id={book_id}, error={e}")
        return redirect("/?error=book_detail_error")

# Google Books 搜尋頁面（重定向到首頁）
@app.route("/google_books_search", methods=["GET"])
def google_books_search():
    if "user" not in session:
        return redirect("/login")
    # 重定向到首頁，帶上搜尋參數
    search_query = request.args.get("q", "").strip()
    if search_query:
        return redirect(f"/?q={search_query}")
    else:
        return redirect("/")

# Google Books API 搜尋
@app.route("/api/google_books/search", methods=["GET"])
def search_google_books():
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        query = request.args.get("q", "").strip()
        if not query:
            return jsonify({"success": False, "error": "請輸入搜尋關鍵字"}), 400
        
        # 檢測是否為 ISBN（移除所有非數字字元後檢查長度）
        import re
        isbn_clean = re.sub(r'[^0-9]', '', query)
        is_isbn = False
        
        # ISBN-10 是 10 位數字，ISBN-13 是 13 位數字
        if len(isbn_clean) == 10 or len(isbn_clean) == 13:
            # 進一步驗證：ISBN-10 的第一位應該是 0-9，ISBN-13 的前三位應該是 978 或 979
            if len(isbn_clean) == 10:
                is_isbn = True
            elif len(isbn_clean) == 13 and (isbn_clean.startswith('978') or isbn_clean.startswith('979')):
                is_isbn = True
        
        # 呼叫 Google Books API
        google_books_url = "https://www.googleapis.com/books/v1/volumes"
        
        # 如果是 ISBN，使用 isbn: 前綴；否則使用原始查詢
        if is_isbn:
            # 使用清理後的 ISBN（移除連字號和空格）
            search_query = f"isbn:{isbn_clean}"
            # ISBN 搜尋不受語言限制
            params = {
                "q": search_query,
                "maxResults": 20
            }
        else:
            params = {
            "q": query,
            "maxResults": 20,
            "langRestrict": "zh-TW"  # 限制為繁體中文書籍
        }
        
        response = requests.get(google_books_url, params=params)
        
        if response.status_code != 200:
            return jsonify({"success": False, "error": "Google Books API 請求失敗"}), 500
        
        data = response.json()
        books = []
        
        if "items" in data:
            current_user = session["user"]
            
            for item in data["items"]:
                volume_info = item.get("volumeInfo", {})
                
                # 提取書籍資訊
                title = volume_info.get("title", "")
                authors = volume_info.get("authors", [])
                isbn_list = []
                
                # 提取 ISBN
                industry_identifiers = volume_info.get("industryIdentifiers", [])
                for identifier in industry_identifiers:
                    isbn_type = identifier.get("type", "")
                    isbn_value = identifier.get("identifier", "")
                    if isbn_type in ["ISBN_13", "ISBN_10"]:
                        isbn_list.append(isbn_value)
                
                # 提取封面圖片
                image_links = volume_info.get("imageLinks", {})
                thumbnail = image_links.get("thumbnail", "") or image_links.get("smallThumbnail", "")
                has_thumbnail = bool(thumbnail)
                if thumbnail:
                    thumbnail = thumbnail.replace("http://", "https://")
                else:
                    # 如果沒有圖片，使用預設圖片
                    thumbnail = "/static/images/book_original.png"
                
                # 提取其他資訊
                description = volume_info.get("description", "")
                published_date = volume_info.get("publishedDate", "")
                publisher = volume_info.get("publisher", "")
                page_count = volume_info.get("pageCount", 0)
                categories = volume_info.get("categories", [])
                
                google_id = item.get("id", "")
                
                # ============================================================
                # 過濾條件：檢查書籍資訊完整性
                # ============================================================
                # 規則：
                # 1. 如果有 ISBN，無論其他資訊是否完整，都要顯示
                # 2. 如果沒有 ISBN，需要同時具備：出版商、作者、封面才能顯示
                # ============================================================
                has_isbn = len(isbn_list) > 0
                has_publisher = bool(publisher and publisher.strip())
                has_author = bool(authors and len(authors) > 0)
                has_cover = has_thumbnail  # 原始 thumbnail 是否存在（不是預設圖片）
                
                # 如果沒有 ISBN，檢查必要資訊是否完整
                if not has_isbn:
                    # 缺少必要資訊，過濾掉這本書
                    if not (has_publisher and has_author and has_cover):
                        continue  # 跳過這本書，不加入結果列表
                
                # 如果有 ISBN 或資訊完整，繼續處理
                
                # ============================================================
                # 算法：計算有多少人提供這本書
                # ============================================================
                # 目標：在 Firestore 資料庫中找到與 Google Books 搜尋結果相同的書籍
                # 並統計有多少不同的用戶提供這本書（排除當前用戶）
                #
                # 匹配策略（按優先級）：
                # 1. ISBN 匹配（最準確，優先使用）
                # 2. 書名相似度匹配 + 作者匹配
                # 3. 書名完全匹配（即使沒有作者資訊）
                #
                # ============================================================
                
                provider_count = 0
                try:
                    books_ref = db.collection("books")
                    if title or isbn_list:
                        # 查詢所有狀態為 "available" 的書籍（最多 500 筆，提高覆蓋率）
                        books_query = books_ref.where("status", "==", "available").limit(500)
                        matching_books = books_query.stream()
                        
                        provider_ids = set()  # 使用 set 避免重複計算同一人
                        
                        # ============================================================
                        # 函數 1：文字標準化（Text Normalization）
                        # ============================================================
                        # 使用共用的標準化函數以確保一致性
                        # ============================================================
                        def normalize_text(text):
                            return normalize_text_for_matching(text)
                        
                        # ============================================================
                        # 函數 2：計算字串相似度（String Similarity）
                        # ============================================================
                        # 使用共用的相似度計算函數以確保一致性
                        # ============================================================
                        def calculate_similarity(str1, str2):
                            return calculate_similarity_for_matching(str1, str2)
                        
                        # ============================================================
                        # 函數 3：ISBN 匹配（ISBN Matching）
                        # ============================================================
                        # 使用共用的 ISBN 匹配函數以確保一致性
                        # ============================================================
                        def match_isbn(isbn1, isbn2):
                            return match_isbn_for_matching(isbn1, isbn2)
                        
                        # 標準化 Google Books 的書名和作者
                        normalized_title = normalize_text(title) if title else ""
                        normalized_authors = [normalize_text(author) for author in authors] if authors else []
                        
                        # ============================================================
                        # 主匹配循環（Main Matching Loop）
                        # ============================================================
                        # 對資料庫中的每本書進行匹配檢查
                        # ============================================================
                        for book in matching_books:
                            book_dict = book.to_dict()
                            book_title = normalize_text(book_dict.get("title", ""))
                            book_author = normalize_text(book_dict.get("author", ""))
                            book_isbn = book_dict.get("isbn", "")
                            
                            # ============================================================
                            # 階段 1：ISBN 匹配（最準確，優先檢查）
                            # ============================================================
                            isbn_match = False
                            if isbn_list and book_isbn:
                                for isbn in isbn_list:
                                    if match_isbn(isbn, book_isbn):
                                        isbn_match = True
                                        break
                            
                            # 如果 ISBN 匹配，直接認為是同一本書（100% 確定）
                            if isbn_match:
                                seller_email = book_dict.get("seller_email", "")
                                if seller_email and seller_email != current_user:
                                    provider_ids.add(seller_email)
                                continue  # 跳過後續檢查
                            
                            # ============================================================
                            # 階段 2：書名相似度匹配
                            # ============================================================
                            title_similarity = 0.0
                            if normalized_title and book_title:
                                title_similarity = calculate_similarity(normalized_title, book_title)
                            
                            # 書名相似度閾值：0.70（70% 相似）
                            # 降低閾值以匹配不同版本的同一本書（平裝/精裝）
                            # 但會結合作者匹配來提高準確度
                            title_match = title_similarity >= 0.70
                            
                            # ============================================================
                            # 階段 3：作者匹配（改進版，處理多作者情況）
                            # ============================================================
                            author_match = False
                            author_similarity_score = 0.0  # 記錄最高作者相似度
                            
                            if normalized_authors and book_author:
                                for author in normalized_authors:
                                    if author:
                                        # 計算作者相似度
                                        author_sim = calculate_similarity(author, book_author)
                                        author_similarity_score = max(author_similarity_score, author_sim)
                                        
                                        # 作者匹配條件（多種方式）：
                                        # 1. 相似度 >= 0.6（60% 相似）
                                        # 2. 完全包含匹配（例如："安東尼" 匹配 "安東尼·聖修伯里"）
                                        # 3. 部分匹配（處理多作者情況，如 "張三, 李四" 匹配 "張三"）
                                        if author_sim >= 0.6:
                                            author_match = True
                                            break
                            
                                        # 完全包含匹配
                                        if author in book_author or book_author in author:
                                            author_match = True
                                            break
                            
                                        # 處理多作者情況（用逗號分隔）
                                        # 例如：book_author = "張三, 李四"，author = "張三"
                                        if ',' in book_author:
                                            authors_list = [a.strip() for a in book_author.split(',')]
                                            if author in authors_list:
                                                author_match = True
                                                break
                                        if ',' in author:
                                            authors_list = [a.strip() for a in author.split(',')]
                                            if book_author in authors_list:
                                                author_match = True
                                            break
                            
                            # ============================================================
                            # 階段 4：綜合判斷（改進版，處理平裝/精裝版本）
                            # ============================================================
                            # 匹配條件（需滿足其一）：
                            # 1. ISBN 匹配（已在階段 1 處理）
                            # 2. 書名完全匹配（相似度 = 1.0）且（作者匹配或沒有作者資訊）
                            # 3. 書名高度相似（相似度 >= 0.85）且作者匹配（嚴格匹配）
                            # 4. 書名中等相似（相似度 >= 0.70）且作者完全匹配（處理平裝/精裝）
                            # ============================================================
                            is_same_book = False
                            
                            if title_similarity == 1.0:  # 書名完全匹配
                                # 完全匹配時，即使沒有作者資訊也認為是同一本書
                                if author_match or not normalized_authors:
                                    is_same_book = True
                            elif title_similarity >= 0.85:  # 書名高度相似（>= 85%）
                                # 高度相似時，需要作者匹配
                                if author_match:
                                    is_same_book = True
                            elif title_similarity >= 0.70:  # 書名中等相似（70-85%）
                                # 中等相似時，需要更嚴格的作者匹配（處理平裝/精裝版本）
                                # 檢查作者是否完全匹配或高度相似
                                strict_author_match = False
                                if normalized_authors and book_author:
                                    for author in normalized_authors:
                                        if author:
                                            author_sim = calculate_similarity(author, book_author)
                                            # 中等書名相似度時，要求更高的作者相似度（0.75）
                                            if author_sim >= 0.75 or author == book_author or book_author == author:
                                                strict_author_match = True
                                                break
                                
                                if strict_author_match:
                                    is_same_book = True
                            
                            if is_same_book:
                                seller_email = book_dict.get("seller_email", "")
                                if seller_email and seller_email != current_user:
                                    provider_ids.add(seller_email)
                        
                        # 最終提供人數 = 不重複的提供者數量
                        provider_count = len(provider_ids)
                except Exception as e:
                    print(f"查詢提供者數量時發生錯誤：{e}")
                    import traceback
                    traceback.print_exc()
                    provider_count = 0
                
                books.append({
                    "google_id": google_id,
                    "title": title,
                    "authors": authors,
                    "isbn": isbn_list[0] if isbn_list else "",
                    "isbn_list": isbn_list,
                    "thumbnail": thumbnail,
                    "description": description,
                    "published_date": published_date,
                    "publisher": publisher,
                    "page_count": page_count,
                    "categories": categories,
                    "provider_count": provider_count
                })
        
        # 按照提供人數從大到小排序，提供人數相同時保持 Google Books 的原始順序
        # 使用穩定的排序，確保有人提供的書優先顯示
        books.sort(key=lambda x: (
            -x.get("provider_count", 0),  # 負數用於降序排序（提供人數多的在前）
            x.get("title", "")  # 提供人數相同時，按書名排序（保持穩定性）
        ))
        
        return jsonify({
            "success": True,
            "books": books,
            "total": len(books)
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"搜尋 Google Books 時發生錯誤：{e}")
        return jsonify({"success": False, "error": str(e)}), 500

# Google Books 書籍詳情頁面
@app.route("/google_book/<google_id>", methods=["GET"])
def google_book_detail(google_id):
    if "user" not in session:
        return redirect("/login")
    
    try:
        # 從 URL 參數獲取書籍資訊
        title = request.args.get("title", "")
        authors = request.args.get("authors", "")
        isbn = request.args.get("isbn", "")
        search_query = request.args.get("search", "")  # 獲取搜尋關鍵字
        
        # 如果沒有提供，從 Google Books API 獲取
        if not title:
            google_books_url = f"https://www.googleapis.com/books/v1/volumes/{google_id}"
            response = requests.get(google_books_url)
            
            if response.status_code == 200:
                data = response.json()
                volume_info = data.get("volumeInfo", {})
                title = volume_info.get("title", "")
                authors = volume_info.get("authors", [])
                if isinstance(authors, list):
                    authors = ", ".join(authors)
                
                industry_identifiers = volume_info.get("industryIdentifiers", [])
                for identifier in industry_identifiers:
                    if identifier.get("type") in ["ISBN_13", "ISBN_10"]:
                        isbn = identifier.get("identifier", "")
                        break
            else:
                return redirect("/?error=book_not_found")
        
        # 查詢 Firestore 中提供這本書的所有用戶（使用與搜尋結果相同的匹配算法）
        current_user = session["user"]
        books_ref = db.collection("books")
        books_query = books_ref.where("status", "==", "available").limit(500)  # 增加查詢數量以匹配搜尋結果
        books = books_query.stream()
        
        # 處理 Google Books 的 ISBN 列表
        google_isbn_list = []
        if isbn:
            google_isbn_list.append(isbn)
        
        # 如果從 Google Books API 獲取，提取所有 ISBN
        if not google_isbn_list or len(google_isbn_list) == 0:
            try:
                google_books_url_temp = f"https://www.googleapis.com/books/v1/volumes/{google_id}"
                response_temp = requests.get(google_books_url_temp)
                if response_temp.status_code == 200:
                    data_temp = response_temp.json()
                    volume_info_temp = data_temp.get("volumeInfo", {})
                    industry_identifiers = volume_info_temp.get("industryIdentifiers", [])
                    for identifier in industry_identifiers:
                        if identifier.get("type") in ["ISBN_13", "ISBN_10"]:
                            google_isbn_list.append(identifier.get("identifier", ""))
            except:
                pass
        
        # 處理作者列表
        google_authors = []
        if authors:
            if isinstance(authors, str):
                google_authors = [a.strip() for a in authors.split(",")]
            elif isinstance(authors, list):
                google_authors = authors
        
        providers = []
        provider_ids = set()  # 使用 set 避免重複計算同一人
        
        for book in books:
            book_dict = book.to_dict()
            book_id = book.id
            book_title = book_dict.get("title", "")
            book_author = book_dict.get("author", "")
            book_isbn = book_dict.get("isbn", "")
            seller_email = book_dict.get("seller_email", "")
            
            # 跳過當前用戶的書籍
            if seller_email == current_user:
                continue
            
            # 使用與搜尋結果相同的匹配算法
            if is_same_book(title, google_authors, google_isbn_list, book_title, book_author, book_isbn):
                # 避免重複計算同一提供者
                if seller_email not in provider_ids:
                    provider_ids.add(seller_email)
                    
                # 處理書籍資料
                book_dict = process_book_data(book_dict)
                book_dict["id"] = book_id
                
                # 獲取賣家顯示名稱
                try:
                    user_ref = db.collection("users").document(seller_email)
                    user_doc = user_ref.get()
                    if user_doc.exists:
                        user_data = user_doc.to_dict()
                        book_dict["seller_display"] = user_data.get("display_name", seller_email.split("@")[0] if "@" in seller_email else seller_email)
                    else:
                        book_dict["seller_display"] = seller_email.split("@")[0] if "@" in seller_email else seller_email
                except:
                    book_dict["seller_display"] = seller_email.split("@")[0] if "@" in seller_email else seller_email
                
                providers.append(book_dict)
        
        # 按創建時間排序
        providers.sort(key=lambda x: x.get("created_at_timestamp", ""), reverse=True)
        
        # 從 Google Books API 獲取詳細資訊
        google_books_url = f"https://www.googleapis.com/books/v1/volumes/{google_id}"
        response = requests.get(google_books_url)
        book_details = {}
        
        if response.status_code == 200:
            data = response.json()
            volume_info = data.get("volumeInfo", {})
            
            image_links = volume_info.get("imageLinks", {})
            thumbnail = image_links.get("thumbnail", "") or image_links.get("smallThumbnail", "")
            if thumbnail:
                thumbnail = thumbnail.replace("http://", "https://")
            else:
                # 如果沒有圖片，使用預設圖片
                thumbnail = "/static/images/book_original.png"
            
            book_details = {
                "title": volume_info.get("title", title),
                "authors": volume_info.get("authors", [authors.split(",")] if authors else []),
                "description": volume_info.get("description", ""),
                "published_date": volume_info.get("publishedDate", ""),
                "publisher": volume_info.get("publisher", ""),
                "page_count": volume_info.get("pageCount", 0),
                "categories": volume_info.get("categories", []),
                "thumbnail": thumbnail,
                "language": volume_info.get("language", ""),
                "preview_link": volume_info.get("previewLink", ""),
                "info_link": volume_info.get("infoLink", "")
            }
            
            # 提取 ISBN
            industry_identifiers = volume_info.get("industryIdentifiers", [])
            isbn_list = []
            for identifier in industry_identifiers:
                if identifier.get("type") in ["ISBN_13", "ISBN_10"]:
                    isbn_list.append(identifier.get("identifier", ""))
            book_details["isbn"] = isbn_list[0] if isbn_list else isbn
            book_details["isbn_list"] = isbn_list
        
        # 查詢該書籍的所有評價
        reviews = []
        try:
            evaluations_ref = db.collection("evaluations")
            book_title = book_details.get("title", title)
            if book_title:
                try:
                    evaluations_query = evaluations_ref.where("book_title", "==", book_title).order_by("created_at", direction=firestore.Query.DESCENDING).limit(50)
                    evaluations = list(evaluations_query.stream())
                except Exception as query_error:
                    # 如果排序失敗，使用簡單查詢
                    print(f"評價查詢排序失敗，使用簡單查詢：{query_error}")
                    evaluations_query = evaluations_ref.where("book_title", "==", book_title).limit(50)
                    evaluations = list(evaluations_query.stream())
                
                for evaluation in evaluations:
                    eval_dict = evaluation.to_dict()
                    eval_dict["id"] = evaluation.id
                    
                    # 處理時間戳記（轉換為 UTC+8）
                    if "created_at" in eval_dict and eval_dict["created_at"]:
                        try:
                            dt = None
                            if hasattr(eval_dict["created_at"], "strftime"):
                                dt = eval_dict["created_at"]
                            elif hasattr(eval_dict["created_at"], "timestamp"):
                                dt = eval_dict["created_at"].to_datetime()
                            
                            if dt:
                                # 轉換為 UTC+8
                                dt_utc8 = convert_to_utc8(dt)
                                eval_dict["created_at"] = dt_utc8.strftime("%Y-%m-%d")
                            else:
                                eval_dict["created_at"] = str(eval_dict["created_at"])[:10]
                        except Exception as e:
                            print(f"處理時間戳記時發生錯誤：{e}")
                            eval_dict["created_at"] = str(eval_dict["created_at"])[:10] if eval_dict["created_at"] else ""
                    
                    reviews.append(eval_dict)
                
                # 計算平均評分
                if reviews:
                    ratings = [r.get("rating", 0) for r in reviews if r.get("rating", 0) > 0]
                    if ratings:
                        avg_rating = sum(ratings) / len(ratings)
                        book_details["avg_rating"] = avg_rating
                    else:
                        book_details["avg_rating"] = 0
                else:
                    book_details["avg_rating"] = 0
        except Exception as e:
            print(f"查詢評價時發生錯誤：{e}")
            reviews = []
            book_details["avg_rating"] = 0
        
        return render_template("google_book_detail.html", 
                             book_details=book_details,
                             providers=providers,
                             google_id=google_id,
                             search_query=search_query,
                             reviews=reviews)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"獲取 Google Books 詳情時發生錯誤：{e}")
        return redirect("/?error=detail_error")

# 搜尋功能
@app.route("/search", methods=["GET"])
def search():
    """將舊的搜尋路由重定向到 Google Books 搜尋"""
    if "user" not in session:
        return redirect("/login")
    
    # 獲取搜尋關鍵字並重定向到 Google Books 搜尋
    search_query = request.args.get("q", "").strip()
    if search_query:
        return redirect(f"/google_books_search?q={search_query}")
    else:
        return redirect("/google_books_search")

# AI 推薦圖書
@app.route("/ai_recommend", methods=["GET", "POST"])
def ai_recommend():
    if "user" not in session:
        return redirect("/login")
        
        current_user = session["user"]
    
    if request.method == "POST":
        department = request.form.get("department", "").strip()
        major = request.form.get("major", "").strip()
        grade = request.form.get("grade", "").strip()
        course_name = request.form.get("course_name", "").strip()
        additional_requirements = request.form.get("additional_requirements", "").strip()
        
        if not course_name:
            return render_template("ai_recommend.html", 
                                 error="請輸入課程名稱",
                                 department=department,
                                 major=major,
                                 grade=grade,
                                 additional_requirements=additional_requirements)
        
        try:
            evaluations_ref = db.collection("evaluations")
            evaluations_query = evaluations_ref.where("book_type", "==", "course").where("course_name", "==", course_name)
            evaluations = list(evaluations_query.stream())
            
            # 過濾系所和年級
            if department:
                evaluations = [e for e in evaluations if e.to_dict().get("department") == department]
            if grade:
                evaluations = [e for e in evaluations if e.to_dict().get("grade") == grade]
            
            # 按書名分組
            book_reviews = {}
            for eval_doc in evaluations:
                eval_dict = eval_doc.to_dict()
                book_title = eval_dict.get("book_title", "")
                if not book_title:
                    continue
                
                if book_title not in book_reviews:
                    book_reviews[book_title] = []
                
                book_reviews[book_title].append({
                    "rating": eval_dict.get("rating", 0),
                    "review_content": eval_dict.get("review_content", ""),
                    "reviewer_email": eval_dict.get("reviewer_email", ""),
                    "course_name": eval_dict.get("course_name", ""),
                    "instructor": eval_dict.get("instructor", ""),
                    "department": eval_dict.get("department", ""),
                    "major": eval_dict.get("major", ""),
                    "grade": eval_dict.get("grade", ""),
                    "created_at": eval_dict.get("created_at", "")
                })
            
            # 為每本書生成推薦
            recommendations = []
            for book_title, reviews in book_reviews.items():
                if not reviews:
                    continue
                    
                avg_rating = sum(r["rating"] for r in reviews) / len(reviews)
                review_count = len(reviews)
                
                # 查詢提供者
                books_ref = db.collection("books")
                books_query = books_ref.where("title", "==", book_title).where("status", "==", "available")
                providers = list(books_query.stream())
                provider_count = len(providers)
                
                # 嘗試使用 AI 生成推薦
                recommendation = generate_ai_recommendation(
                    book_title, reviews, avg_rating, review_count, 
                    provider_count, course_name, department, grade, 
                    additional_requirements
                )
                
                # 如果 AI 生成失敗，使用規則生成
                if not recommendation:
                    recommendation = generate_human_recommendation(
                        book_title, reviews, avg_rating, review_count, 
                        provider_count, course_name, department, grade, 
                        additional_requirements
                    )
                
                # 獲取書籍詳細資訊
                if providers:
                    book_dict = providers[0].to_dict()
                    recommendation["book_id"] = providers[0].id
                    recommendation["author"] = book_dict.get("author", "")
                    recommendation["isbn"] = book_dict.get("isbn", "")
                    recommendation["front_image"] = book_dict.get("front_image", "/static/images/book_original.png")
                else:
                    # 從 Google Books API 獲取
                    try:
                        google_books_url = f"https://www.googleapis.com/books/v1/volumes?q=intitle:{book_title}&maxResults=1"
                        response = requests.get(google_books_url)
                        if response.status_code == 200:
                            data = response.json()
                            items = data.get("items", [])
                            if items:
                                volume_info = items[0].get("volumeInfo", {})
                                recommendation["author"] = ", ".join(volume_info.get("authors", []))
                                industry_identifiers = volume_info.get("industryIdentifiers", [])
                                recommendation["isbn"] = industry_identifiers[0].get("identifier", "") if industry_identifiers else ""
                                image_links = volume_info.get("imageLinks", {})
                                recommendation["front_image"] = image_links.get("thumbnail", "/static/images/book_original.png")
                            else:
                                recommendation["author"] = "未知"
                                recommendation["isbn"] = ""
                                recommendation["front_image"] = "/static/images/book_original.png"
                        else:
                            recommendation["author"] = "未知"
                            recommendation["isbn"] = ""
                            recommendation["front_image"] = "/static/images/book_original.png"
                    except Exception as e:
                        print(f"從 Google Books API 獲取書籍資訊失敗：{e}")
                        recommendation["author"] = "未知"
                        recommendation["isbn"] = ""
                        recommendation["front_image"] = "/static/images/book_original.png"
                
                recommendation["book_title"] = book_title
                recommendations.append(recommendation)
            
            # 按推薦分數排序
            recommendations.sort(key=lambda x: x.get("recommendation_score", 0), reverse=True)
            
            return render_template("ai_recommend.html",
                                 recommendations=recommendations,
                                 course_name=course_name,
                                 department=department,
                                 major=major,
                                 grade=grade,
                                 additional_requirements=additional_requirements)
        
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"AI 推薦時發生錯誤：{e}")
            return render_template("ai_recommend.html",
                                 error="查詢時發生錯誤，請稍後再試",
                                 department=department,
                                 major=major,
                                 grade=grade,
                                 course_name=course_name,
                                 additional_requirements=additional_requirements)
    
    # GET 請求：顯示表單
    if "user" not in session:
        return redirect("/login")
    current_user = session["user"]
    try:
        user_ref = db.collection("users").document(current_user)
        user_doc = user_ref.get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            default_department = user_data.get("department", "")
            default_major = user_data.get("major", "")
            default_grade = user_data.get("grade", "")
        else:
            default_department = ""
            default_major = ""
            default_grade = ""
    except:
        default_department = ""
        default_major = ""
        default_grade = ""
    
    return render_template("ai_recommend.html",
                         department=default_department,
                         major=default_major,
                         grade=default_grade)


# 換書資訊詳細頁面（必須在 /wanted_book 之前定義，避免路由衝突）
@app.route("/wanted_book/<wanted_book_id>", methods=["GET"])
def wanted_book_detail(wanted_book_id):
    if "user" not in session:
        return redirect("/login")
    
    try:
        current_user = session["user"]
        
        # 獲取換書資訊
        wanted_book_ref = db.collection("wanted_books").document(wanted_book_id)
        wanted_book_doc = wanted_book_ref.get()
        
        if not wanted_book_doc.exists:
            return redirect("/?error=wanted_book_not_found")
        
        wanted_book_dict = wanted_book_doc.to_dict()
        wanted_book_dict["id"] = wanted_book_doc.id
        
        # 處理時間戳記（轉換為 UTC+8）
        if "created_at" in wanted_book_dict and wanted_book_dict["created_at"]:
            try:
                dt = None
                if hasattr(wanted_book_dict["created_at"], "strftime"):
                    dt = wanted_book_dict["created_at"]
                elif hasattr(wanted_book_dict["created_at"], "timestamp"):
                    dt = wanted_book_dict["created_at"].to_datetime()
                
                if dt:
                    # 轉換為 UTC+8
                    dt_utc8 = convert_to_utc8(dt)
                    wanted_book_dict["created_at"] = dt_utc8.strftime("%Y-%m-%d")
                else:
                    wanted_book_dict["created_at"] = str(wanted_book_dict["created_at"])[:10]
            except Exception as e:
                print(f"處理時間戳記時發生錯誤：{e}")
                wanted_book_dict["created_at"] = str(wanted_book_dict["created_at"])[:10] if wanted_book_dict["created_at"] else ""
        else:
            wanted_book_dict["created_at"] = ""
        
        # 獲取發布者資訊
        requester_email = wanted_book_dict.get("requester_email", "")
        requester_display = ""
        requester_avatar = "user_cat01.png"
        
        if requester_email:
            if "@" in requester_email:
                requester_display = requester_email.split("@")[0]
            else:
                requester_display = requester_email
            
            # 獲取用戶資料
            try:
                user_ref = db.collection("users").document(requester_email)
                user_doc = user_ref.get()
                if user_doc.exists:
                    user_data = user_doc.to_dict()
                    if user_data.get("display_name"):
                        requester_display = user_data["display_name"]
                    if user_data.get("avatar"):
                        requester_avatar = user_data["avatar"]
            except:
                pass
        
        # 檢查是否已收藏
        is_favorited = False
        try:
            favorites_ref = db.collection("favorites")
            favorites_query = favorites_ref.where("user_email", "==", current_user).where("item_id", "==", wanted_book_id).where("item_type", "==", "wanted_book").limit(1)
            favorites = list(favorites_query.stream())
            is_favorited = len(favorites) > 0
        except:
            pass
        
        # 檢查是否為發布者本人
        is_owner = (requester_email == current_user)
        
        return render_template("wanted_book_detail.html",
                             wanted_book=wanted_book_dict,
                             requester_display=requester_display,
                             requester_email=requester_email,
                             requester_avatar=requester_avatar,
                             is_favorited=is_favorited,
                             is_owner=is_owner)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return redirect("/?error=wanted_book_detail_error")

# 我想要書（創建新換書資訊）
@app.route("/wanted_book", methods=["GET", "POST"])
def wanted_book():
    if "user" not in session:
        return redirect("/login")
    
    if request.method == "POST":
        try:
            # 獲取表單資料
            book_title = request.form.get("book_title", "").strip()
            author = request.form.get("author", "").strip()
            isbn = request.form.get("isbn", "").strip()
            exchange_method = request.form.get("exchange_method", "").strip()
            remarks = request.form.get("remarks", "").strip()
            
            # 資料驗證
            if not book_title:
                return render_template("wanted_book.html", error="請輸入書名。")
            if not author:
                return render_template("wanted_book.html", error="請輸入作者。")
            
            # 儲存到 Firestore - wanted_books collection
            # 不再需要 status 字段，因為現在直接從資料庫刪除
            wanted_book_data = {
                "book_title": book_title,
                "author": author,
                "isbn": isbn,
                "exchange_method": exchange_method,
                "remarks": remarks,
                "requester_email": session["user"],
                "created_at": firestore.SERVER_TIMESTAMP
            }
            
            wanted_book_ref = db.collection("wanted_books").document()
            wanted_book_ref.set(wanted_book_data)
            
            return redirect("/?success=wanted_book_added")
        except Exception as e:
            import traceback
            error_msg = str(e)
            traceback.print_exc()
            return render_template("wanted_book.html", error=f"提交失敗：{error_msg}。請檢查控制台日誌獲取更多資訊。")
    
    return render_template("wanted_book.html")

# 想寫書評
@app.route("/write_review", methods=["GET", "POST"])
def write_review():
    if "user" not in session:
        return redirect("/login")
    
    if request.method == "POST":
        try:
            # 獲取表單資料
            book_title = request.form.get("book_title", "").strip()
            rating_str = request.form.get("rating", "4")
            try:
                rating = int(rating_str) if rating_str else 4
            except ValueError:
                rating = 4
            
            book_type = request.form.get("book_type", "").strip()
            course_type = request.form.get("course_type", "").strip()
            department = request.form.get("department", "").strip()
            major = request.form.get("major", "").strip()
            grade = request.form.get("grade", "").strip()
            course_name = request.form.get("course_name", "").strip()
            instructor = request.form.get("instructor", "").strip()
            review_content = request.form.get("review_content", "").strip()
            
            # 基本資料驗證
            if not book_title:
                return render_template("write_review.html", error="請輸入書名。")
            if not book_type:
                return render_template("write_review.html", error="請選擇書籍類型。")
            if not review_content:
                return render_template("write_review.html", error="請輸入詳細內容。")
            
            # 根據書籍類型進行驗證
            if book_type == "course":
                # 課用書：需要課程類型、課程名稱、授課老師
                if not course_type:
                    return render_template("write_review.html", error="請選擇課程類型。")
                if not course_name:
                    return render_template("write_review.html", error="請輸入課程名稱。")
                if not instructor:
                    return render_template("write_review.html", error="請輸入授課老師。")
                
                # 系所課程：需要系所、科系、年級
                if course_type == "department":
                    if not department:
                        return render_template("write_review.html", error="請選擇系所。")
                    if not major:
                        return render_template("write_review.html", error="請選擇科系。")
                    if not grade:
                        return render_template("write_review.html", error="請選擇年級。")
            
            # 儲存到 Firestore - evaluations collection
            evaluation_data = {
                "book_title": book_title,
                "rating": rating,
                "book_type": book_type,
                "review_content": review_content,
                "reviewer_email": session["user"],
                "created_at": firestore.SERVER_TIMESTAMP
            }
            
            # 如果是課用書，添加課程相關資訊
            if book_type == "course":
                evaluation_data["course_type"] = course_type
                evaluation_data["course_name"] = course_name
                evaluation_data["instructor"] = instructor
                
                # 只有系所課程才需要系所、科系、年級
                if course_type == "department":
                    evaluation_data["department"] = department
                    evaluation_data["major"] = major
                    evaluation_data["grade"] = grade
            
            evaluation_ref = db.collection("evaluations").document()
            evaluation_ref.set(evaluation_data)
            
            return redirect("/?success=review_added")
        except Exception as e:
            import traceback
            error_msg = str(e)
            traceback.print_exc()
            return render_template("write_review.html", error=f"提交失敗：{error_msg}。請檢查控制台日誌獲取更多資訊。")
    
    return render_template("write_review.html")

# 編輯書籍
@app.route("/edit_book/<book_id>", methods=["GET", "POST"])
def edit_book(book_id):
    if "user" not in session:
        return redirect("/login")
    
    try:
        # 獲取書籍資料
        book_ref = db.collection("books").document(book_id)
        book_doc = book_ref.get()
        
        if not book_doc.exists:
            return redirect("/profile?error=book_not_found")
        
        book_dict = book_doc.to_dict()
        
        # 檢查是否為書籍所有者
        if book_dict.get("seller_email") != session["user"]:
            return redirect("/profile?error=no_permission")
        
        if request.method == "POST":
            try:
                # 獲取表單資料
                book_title = request.form.get("book_title", "").strip()
                author = request.form.get("author", "").strip()
                isbn = request.form.get("isbn", "").strip()
                condition = request.form.get("condition", "")
                exchange_method = request.form.get("exchange_method", "").strip()
                remarks = request.form.get("remarks", "").strip()
                
                # 資料驗證
                if not book_title:
                    return render_template("edit_book.html", book=book_dict, error="請輸入書名。")
                if not author:
                    return render_template("edit_book.html", book=book_dict, error="請輸入作者。")
                if not condition:
                    return render_template("edit_book.html", book=book_dict, error="請選擇書況。")
                
                # 更新書籍資料
                update_data = {
                    "title": book_title,
                    "author": author,
                    "isbn": isbn,
                    "condition": condition,
                    "exchange_method": exchange_method,
                    "remarks": remarks,
                }
                
                # 處理圖片上傳到 Firebase Storage
                front_image = request.files.get("front_image")
                back_image = request.files.get("back_image")
                
                # 上傳封面圖片（如果有新圖片）
                if front_image and front_image.filename:
                    try:
                        front_image_url = upload_image_to_firebase_storage(front_image, session["user"], "front")
                        update_data["front_image"] = front_image_url
                        print(f"✓ 封面圖片已更新: {front_image_url}")
                    except Exception as e:
                        print(f"❌ 上傳封面圖片失敗: {e}")
                        import traceback
                        traceback.print_exc()
                
                # 上傳封底圖片（如果有新圖片）
                if back_image and back_image.filename:
                    try:
                        back_image_url = upload_image_to_firebase_storage(back_image, session["user"], "back")
                        update_data["back_image"] = back_image_url
                        print(f"✓ 封底圖片已更新: {back_image_url}")
                    except Exception as e:
                        print(f"❌ 上傳封底圖片失敗: {e}")
                        import traceback
                        traceback.print_exc()
                
                book_ref.update(update_data)
                
                return redirect("/profile?success=book_updated")
            except Exception as e:
                import traceback
                traceback.print_exc()
                return render_template("edit_book.html", book=book_dict, error=f"更新失敗：{str(e)}")
        
        # GET 請求，顯示編輯表單
        book_dict["id"] = book_doc.id
        return render_template("edit_book.html", book=book_dict)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return redirect("/profile?error=edit_book_error")

# 刪除書籍
@app.route("/delete_book/<book_id>", methods=["DELETE"])
def delete_book(book_id):
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        # 獲取書籍資料
        book_ref = db.collection("books").document(book_id)
        book_doc = book_ref.get()
        
        if not book_doc.exists:
            return jsonify({"success": False, "error": "書籍不存在"}), 404
        
        book_dict = book_doc.to_dict()
        
        # 檢查是否為書籍所有者
        if book_dict.get("seller_email") != session["user"]:
            return jsonify({"success": False, "error": "沒有權限"}), 403
        
        # 1. 刪除相關的評價（evaluation_id）
        evaluation_id = book_dict.get("evaluation_id", "")
        if evaluation_id:
            try:
                eval_ref = db.collection("evaluations").document(evaluation_id)
                eval_doc = eval_ref.get()
                if eval_doc.exists:
                    eval_ref.delete()
                    print(f"✓ 已刪除相關評價: {evaluation_id}")
            except Exception as e:
                print(f"⚠ 刪除評價時發生錯誤: {e}")
        
        # 2. 刪除所有收藏該書籍的記錄（favorites）
        try:
            favorites_ref = db.collection("favorites")
            # 查詢舊格式（book_id）和新格式（item_id + item_type）
            favorites_query1 = favorites_ref.where("book_id", "==", book_id)
            favorites_query2 = favorites_ref.where("item_id", "==", book_id).where("item_type", "==", "book")
            favorites = list(favorites_query1.stream()) + list(favorites_query2.stream())
            
            deleted_favorites_count = 0
            favorite_ids = set()  # 避免重複刪除
            for favorite in favorites:
                try:
                    if favorite.id not in favorite_ids:
                        favorite.reference.delete()
                        deleted_favorites_count += 1
                        favorite_ids.add(favorite.id)
                except Exception as e:
                    print(f"⚠ 刪除收藏記錄時發生錯誤: {e}")
            
            if deleted_favorites_count > 0:
                print(f"✓ 已刪除 {deleted_favorites_count} 筆收藏記錄")
        except Exception as e:
            print(f"⚠ 查詢收藏記錄時發生錯誤: {e}")
        
        # 3. 刪除 Firebase Storage 中的圖片
        try:
            bucket_name = "book-exchange-d4351.firebasestorage.app"
            bucket = storage.bucket(bucket_name)
            
            # 刪除封面圖片
            front_image = book_dict.get("front_image", "")
            if front_image and ("firebasestorage.app" in front_image or "firebasestorage.googleapis.com" in front_image):
                try:
                    # 從 URL 中提取檔案路徑
                    # URL 格式: https://firebasestorage.googleapis.com/v0/b/bucket/o/path%2Fto%2Ffile?alt=media&token=...
                    import urllib.parse
                    file_path = None
                    
                    if "firebasestorage.googleapis.com" in front_image:
                        # 提取路徑部分
                        if "/o/" in front_image:
                            path_part = front_image.split("/o/")[1].split("?")[0]
                            file_path = urllib.parse.unquote(path_part)
                    elif front_image.startswith("books/"):
                        # 直接使用路徑（新格式）
                        file_path = front_image
                    elif front_image.startswith("book_images/"):
                        # 舊格式路徑
                        file_path = front_image
                    
                    if file_path:
                        blob = bucket.blob(file_path)
                        if blob.exists():
                            blob.delete()
                            print(f"✓ 已刪除封面圖片: {file_path}")
                        else:
                            print(f"⚠ 封面圖片不存在: {file_path}")
                except Exception as e:
                    print(f"⚠ 刪除封面圖片時發生錯誤: {e}")
            
            # 刪除封底圖片
            back_image = book_dict.get("back_image", "")
            if back_image and ("firebasestorage.app" in back_image or "firebasestorage.googleapis.com" in back_image):
                try:
                    import urllib.parse
                    file_path = None
                    
                    if "firebasestorage.googleapis.com" in back_image:
                        if "/o/" in back_image:
                            path_part = back_image.split("/o/")[1].split("?")[0]
                            file_path = urllib.parse.unquote(path_part)
                    elif back_image.startswith("books/"):
                        file_path = back_image
                    elif back_image.startswith("book_images/"):
                        file_path = back_image
                    
                    if file_path:
                        blob = bucket.blob(file_path)
                        if blob.exists():
                            blob.delete()
                            print(f"✓ 已刪除封底圖片: {file_path}")
                        else:
                            print(f"⚠ 封底圖片不存在: {file_path}")
                except Exception as e:
                    print(f"⚠ 刪除封底圖片時發生錯誤: {e}")
        except Exception as e:
            print(f"⚠ 刪除圖片時發生錯誤: {e}")
        
        # 4. 最後刪除書籍本身
        book_ref.delete()
        print(f"✓ 已刪除書籍: {book_id}")
        
        return jsonify({"success": True, "message": "書籍及相關資料已刪除"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

# 編輯想要書
@app.route("/edit_wanted_book/<wanted_book_id>", methods=["GET", "POST"])
def edit_wanted_book(wanted_book_id):
    if "user" not in session:
        return redirect("/login")
    
    try:
        # 獲取想要書資料
        wanted_book_ref = db.collection("wanted_books").document(wanted_book_id)
        wanted_book_doc = wanted_book_ref.get()
        
        if not wanted_book_doc.exists:
            return redirect("/profile?error=wanted_book_not_found")
        
        wanted_book_dict = wanted_book_doc.to_dict()
        
        # 檢查是否為需求者
        if wanted_book_dict.get("requester_email") != session["user"]:
            return redirect("/profile?error=no_permission")
        
        if request.method == "POST":
            try:
                # 獲取表單資料
                book_title = request.form.get("book_title", "").strip()
                author = request.form.get("author", "").strip()
                isbn = request.form.get("isbn", "").strip()
                exchange_method = request.form.get("exchange_method", "").strip()
                remarks = request.form.get("remarks", "").strip()
                
                # 資料驗證
                if not book_title:
                    return render_template("edit_wanted_book.html", wanted_book=wanted_book_dict, error="請輸入書名。")
                if not author:
                    return render_template("edit_wanted_book.html", wanted_book=wanted_book_dict, error="請輸入作者。")
                
                # 更新想要書資料
                update_data = {
                    "book_title": book_title,
                    "author": author,
                    "isbn": isbn,
                    "exchange_method": exchange_method,
                    "remarks": remarks,
                }
                
                wanted_book_ref.update(update_data)
                
                return redirect("/profile?success=wanted_book_updated")
            except Exception as e:
                import traceback
                traceback.print_exc()
                return render_template("edit_wanted_book.html", wanted_book=wanted_book_dict, error=f"更新失敗：{str(e)}")
        
        # GET 請求，顯示編輯表單
        wanted_book_dict["id"] = wanted_book_doc.id
        return render_template("edit_wanted_book.html", wanted_book=wanted_book_dict)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return redirect("/profile?error=edit_wanted_book_error")


# 刪除想要書
@app.route("/delete_wanted_book/<wanted_book_id>", methods=["DELETE"])
def delete_wanted_book(wanted_book_id):
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        # 獲取想要書資料
        wanted_book_ref = db.collection("wanted_books").document(wanted_book_id)
        wanted_book_doc = wanted_book_ref.get()
        
        if not wanted_book_doc.exists:
            return jsonify({"success": False, "error": "需求不存在"}), 404
        
        wanted_book_dict = wanted_book_doc.to_dict()
        
        # 檢查是否為需求者
        if wanted_book_dict.get("requester_email") != session["user"]:
            return jsonify({"success": False, "error": "沒有權限"}), 403
        
        # 直接從資料庫中刪除想要書
        wanted_book_ref.delete()
        
        return jsonify({"success": True, "message": "書籍需求已刪除"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

# 編輯書評
@app.route("/edit_review/<review_id>", methods=["GET", "POST"])
def edit_review(review_id):
    if "user" not in session:
        return redirect("/login")
    
    try:
        # 獲取書評資料
        review_ref = db.collection("evaluations").document(review_id)
        review_doc = review_ref.get()
        
        if not review_doc.exists:
            return redirect("/profile?error=review_not_found")
        
        review_dict = review_doc.to_dict()
        
        # 檢查是否為書評作者
        if review_dict.get("reviewer_email") != session["user"]:
            return redirect("/profile?error=no_permission")
        
        if request.method == "POST":
            try:
                # 獲取表單資料
                book_title = request.form.get("book_title", "").strip()
                rating_str = request.form.get("rating", "4")
                try:
                    rating = int(rating_str) if rating_str else 4
                except ValueError:
                    rating = 4
                
                book_type = request.form.get("book_type", "").strip()
                course_type = request.form.get("course_type", "").strip()
                department = request.form.get("department", "").strip()
                major = request.form.get("major", "").strip()
                grade = request.form.get("grade", "").strip()
                course_name = request.form.get("course_name", "").strip()
                instructor = request.form.get("instructor", "").strip()
                review_content = request.form.get("review_content", "").strip()
                
                # 基本資料驗證
                if not book_title:
                    return render_template("edit_review.html", review=review_dict, error="請輸入書名。")
                if not book_type:
                    return render_template("edit_review.html", review=review_dict, error="請選擇書籍類型。")
                if not review_content:
                    return render_template("edit_review.html", review=review_dict, error="請輸入詳細內容。")
                
                # 根據書籍類型進行驗證
                if book_type == "course":
                    # 課用書：需要課程類型、課程名稱、授課老師
                    if not course_type:
                        return render_template("edit_review.html", review=review_dict, error="請選擇課程類型。")
                    if not course_name:
                        return render_template("edit_review.html", review=review_dict, error="請輸入課程名稱。")
                    if not instructor:
                        return render_template("edit_review.html", review=review_dict, error="請輸入授課老師。")
                    
                    # 系所課程：需要系所、科系、年級
                    if course_type == "department":
                        if not department:
                            return render_template("edit_review.html", review=review_dict, error="請選擇系所。")
                        if not major:
                            return render_template("edit_review.html", review=review_dict, error="請選擇科系。")
                        if not grade:
                            return render_template("edit_review.html", review=review_dict, error="請選擇年級。")
                
                # 更新書評資料
                update_data = {
                    "book_title": book_title,
                    "rating": rating,
                    "book_type": book_type,
                    "review_content": review_content,
                }
                
                # 如果是課用書，添加課程相關資訊
                if book_type == "course":
                    update_data["course_type"] = course_type
                    update_data["course_name"] = course_name
                    update_data["instructor"] = instructor
                    
                    # 只有系所課程才需要系所、科系、年級
                    if course_type == "department":
                        update_data["department"] = department
                        update_data["major"] = major
                        update_data["grade"] = grade
                    else:
                        # 如果不是系所課程，清除這些欄位
                        update_data["department"] = firestore.DELETE_FIELD
                        update_data["major"] = firestore.DELETE_FIELD
                        update_data["grade"] = firestore.DELETE_FIELD
                else:
                    # 如果是課外書，清除所有課程相關欄位
                    update_data["course_type"] = firestore.DELETE_FIELD
                    update_data["course_name"] = firestore.DELETE_FIELD
                    update_data["instructor"] = firestore.DELETE_FIELD
                    update_data["department"] = firestore.DELETE_FIELD
                    update_data["major"] = firestore.DELETE_FIELD
                    update_data["grade"] = firestore.DELETE_FIELD
                
                review_ref.update(update_data)
                
                return redirect("/profile?success=review_updated")
            except Exception as e:
                import traceback
                traceback.print_exc()
                return render_template("edit_review.html", review=review_dict, error=f"更新失敗：{str(e)}")
        
        # GET 請求，顯示編輯表單
        review_dict["id"] = review_doc.id
        return render_template("edit_review.html", review=review_dict)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return redirect("/profile?error=edit_review_error")

# 刪除書評
@app.route("/delete_review/<review_id>", methods=["DELETE"])
def delete_review(review_id):
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        # 獲取書評資料
        review_ref = db.collection("evaluations").document(review_id)
        review_doc = review_ref.get()
        
        if not review_doc.exists:
            return jsonify({"success": False, "error": "書評不存在"}), 404
        
        review_dict = review_doc.to_dict()
        
        # 檢查是否為書評作者
        if review_dict.get("reviewer_email") != session["user"]:
            return jsonify({"success": False, "error": "沒有權限"}), 403
        
        # 1. 查找並更新所有引用此評價的書籍（清空 evaluation_id）
        try:
            books_ref = db.collection("books")
            books_query = books_ref.where("evaluation_id", "==", review_id)
            books = books_query.stream()
            
            updated_books_count = 0
            for book in books:
                try:
                    book.reference.update({"evaluation_id": firestore.DELETE_FIELD})
                    updated_books_count += 1
                    print(f"✓ 已更新書籍 {book.id} 的 evaluation_id")
                except Exception as e:
                    print(f"⚠ 更新書籍 evaluation_id 時發生錯誤: {e}")
            
            if updated_books_count > 0:
                print(f"✓ 已更新 {updated_books_count} 本書籍的 evaluation_id")
        except Exception as e:
            print(f"⚠ 查詢相關書籍時發生錯誤: {e}")
        
        # 2. 刪除書評本身
        review_ref.delete()
        print(f"✓ 已刪除書評: {review_id}")
        
        return jsonify({"success": True, "message": "書評及相關資料已刪除"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

# 新增書籍
@app.route("/add_book", methods=["GET", "POST"])
def add_book():
    if "user" not in session:
        return redirect("/login")  # 未登入則跳轉到登入頁
    
    if request.method == "POST":
        try:
            # 獲取表單資料
            book_title = request.form.get("book_title", "").strip()
            author = request.form.get("author", "").strip()
            isbn = request.form.get("isbn", "").strip()
            condition = request.form.get("condition", "")
            exchange_method = request.form.get("exchange_method", "").strip()
            remarks = request.form.get("remarks", "").strip()
            
            # 評價資料
            rating_str = request.form.get("rating", "4")
            try:
                rating = int(rating_str) if rating_str else 4
            except ValueError:
                rating = 4
            
            book_type = request.form.get("book_type", "").strip()
            course_type = request.form.get("course_type", "").strip()
            department = request.form.get("department", "").strip()
            major = request.form.get("major", "").strip()
            grade = request.form.get("grade", "").strip()
            course_name = request.form.get("course_name", "").strip()
            instructor = request.form.get("instructor", "").strip()
            review_content = request.form.get("review_content", "").strip()
            
            # 資料驗證
            if not book_title:
                return render_template("add_book.html", error="請輸入書名。")
            if not author:
                return render_template("add_book.html", error="請輸入作者。")
            if not condition:
                return render_template("add_book.html", error="請選擇書況。")
            if not book_type:
                return render_template("add_book.html", error="請選擇書籍類型。")
            if not review_content:
                return render_template("add_book.html", error="請輸入詳細內容。")
            
            # 根據書籍類型進行驗證
            if book_type == "course":
                # 課用書：需要課程類型、課程名稱、授課老師
                if not course_type:
                    return render_template("add_book.html", error="請選擇課程類型。")
                if not course_name:
                    return render_template("add_book.html", error="請輸入課程名稱。")
                if not instructor:
                    return render_template("add_book.html", error="請輸入授課老師。")
                
                # 系所課程：需要系所、科系、年級
                if course_type == "department":
                    if not department:
                        return render_template("add_book.html", error="請選擇系所。")
                    if not major:
                        return render_template("add_book.html", error="請選擇科系。")
                    if not grade:
                        return render_template("add_book.html", error="請選擇年級。")
            
            # 處理圖片上傳到 Firebase Storage
            front_image = request.files.get("front_image")
            back_image = request.files.get("back_image")
            
            front_image_url = ""
            back_image_url = ""
            
            # 上傳封面圖片
            if front_image and front_image.filename:
                try:
                    front_image_url = upload_image_to_firebase_storage(front_image, session["user"], "front")
                    print(f"✓ 封面圖片已上傳: {front_image_url}")
                except Exception as e:
                    print(f"❌ 上傳封面圖片失敗: {e}")
                    import traceback
                    traceback.print_exc()
            
            # 上傳封底圖片
            if back_image and back_image.filename:
                try:
                    back_image_url = upload_image_to_firebase_storage(back_image, session["user"], "back")
                    print(f"✓ 封底圖片已上傳: {back_image_url}")
                except Exception as e:
                    print(f"❌ 上傳封底圖片失敗: {e}")
                    import traceback
                    traceback.print_exc()
            
            # 創建書籍資料
            book_data = {
                "title": book_title,
                "author": author,
                "isbn": isbn,
                "condition": condition,
                "exchange_method": exchange_method,
                "remarks": remarks,
                "front_image": front_image_url,
                "back_image": back_image_url,
                "seller_email": session["user"].strip().lower(),  # 標準化 email 格式
                "created_at": firestore.SERVER_TIMESTAMP,
                "status": "available"
            }
            
            # 創建評價資料
            evaluation_data = {
                "book_title": book_title,
                "rating": rating,
                "book_type": book_type,
                "review_content": review_content,
                "reviewer_email": session["user"],
                "created_at": firestore.SERVER_TIMESTAMP
            }
            
            # 如果是課用書，添加課程相關資訊
            if book_type == "course":
                evaluation_data["course_type"] = course_type
                evaluation_data["course_name"] = course_name
                evaluation_data["instructor"] = instructor
                
                # 只有系所課程才需要系所、科系、年級
                if course_type == "department":
                    evaluation_data["department"] = department
                    evaluation_data["major"] = major
                    evaluation_data["grade"] = grade
            
            # 儲存到 Firestore
            print(f"準備儲存書籍資料: {book_title}")
            print(f"賣家電子郵件: {session['user']}")
            
            # 儲存書籍資料
            book_ref = db.collection("books").document()
            book_ref.set(book_data)
            book_id = book_ref.id
            print(f"✓ 書籍已儲存到 Firestore，ID: {book_id}")
            
            # 儲存評價資料
            evaluation_ref = db.collection("evaluations").document()
            evaluation_data["book_id"] = book_id  # 將書籍 ID 加入評價資料
            evaluation_ref.set(evaluation_data)
            evaluation_id = evaluation_ref.id
            print(f"✓ 評價已儲存到 Firestore，ID: {evaluation_id}")
            
            # 將評價 ID 關聯到書籍
            book_ref.update({"evaluation_id": evaluation_id})
            print(f"✓ 評價 ID {evaluation_id} 已關聯到書籍 {book_id}")
            
            print("=" * 50)
            print("書籍和評價已成功儲存到 Firestore！")
            print(f"書籍 ID: {book_id}")
            print(f"評價 ID: {evaluation_id}")
            print("=" * 50)
            
            return redirect("/")  # 提交成功後返回首頁
            
        except Exception as e:
            import traceback
            error_msg = str(e)
            traceback.print_exc()  # 打印完整的錯誤堆疊
            print(f"❌ 錯誤詳情: {error_msg}")
            return render_template("add_book.html", error=f"提交失敗：{error_msg}。請檢查控制台日誌獲取更多資訊。")
    
    return render_template("add_book.html")  # 渲染新增書籍頁面
# ============================================================
# 書籍匹配算法（共用函數）
# ============================================================

def normalize_text_for_matching(text):
    """
    文字標準化（用於書籍匹配）
    移除版本相關詞彙，統一格式
    """
    if not text:
        return ""
    import re
    # 轉為小寫
    text = text.lower()
    
    # 移除版本相關詞彙（這些詞不會影響書籍的實質內容）
    version_keywords = [
        r'平裝', r'精裝', r'新版', r'修訂版', r'增訂版', r'再版',
        r'初版', r'二版', r'三版', r'第\d+版', r'第\d+刷',
        r'paperback', r'hardcover', r'hardback', r'精裝版', r'平裝版',
        r'新版', r'新版本', r'修訂', r'增訂', r'再版', r'初版',
        r'vol\.?\d+', r'volume\s+\d+', r'第\d+卷', r'第\d+冊'
    ]
    for keyword in version_keywords:
        text = re.sub(keyword, '', text, flags=re.IGNORECASE)
    
    # 移除標點符號和特殊字元，只保留中文、英文、數字和空格
    text = re.sub(r'[^\w\s\u4e00-\u9fff]', '', text)
    # 將多個空格合併為一個
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def calculate_similarity_for_matching(str1, str2):
    """
    計算字串相似度（用於書籍匹配）
    使用 Jaccard 相似度 + 字元序列匹配
    """
    if not str1 or not str2:
        return 0.0
    
    # 完全匹配
    if str1 == str2:
        return 1.0
    
    # 計算 Jaccard 相似度（基於字元集合）
    set1 = set(str1)
    set2 = set(str2)
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    jaccard = intersection / union if union > 0 else 0.0
    
    # 計算最長公共子串長度比例
    def longest_common_substring(s1, s2):
        m, n = len(s1), len(s2)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        max_len = 0
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if s1[i-1] == s2[j-1]:
                    dp[i][j] = dp[i-1][j-1] + 1
                    max_len = max(max_len, dp[i][j])
        return max_len
    
    lcs_len = longest_common_substring(str1, str2)
    min_len = min(len(str1), len(str2))
    lcs_ratio = lcs_len / min_len if min_len > 0 else 0.0
    
    # 包含匹配（一個字串完全包含在另一個中）
    contains_ratio = 0.0
    if str1 in str2:
        contains_ratio = len(str1) / len(str2)
    elif str2 in str1:
        contains_ratio = len(str2) / len(str1)
    
    # 綜合相似度：加權平均
    similarity = (jaccard * 0.4) + (lcs_ratio * 0.4) + (contains_ratio * 0.2)
    
    return similarity

def match_isbn_for_matching(isbn1, isbn2):
    """
    ISBN 匹配（處理 ISBN-10 和 ISBN-13 的轉換）
    """
    if not isbn1 or not isbn2:
        return False
    
    # 清理 ISBN（移除連字號和空格）
    clean1 = isbn1.replace("-", "").replace(" ", "").lower()
    clean2 = isbn2.replace("-", "").replace(" ", "").lower()
    
    # 完全匹配
    if clean1 == clean2:
        return True
    
    # ISBN-13 轉 ISBN-10 匹配
    if len(clean1) == 13 and len(clean2) == 10:
        if clean1.startswith('978') or clean1.startswith('979'):
            if clean1[3:] == clean2:
                return True
    
    if len(clean1) == 10 and len(clean2) == 13:
        if clean2.startswith('978') or clean2.startswith('979'):
            if clean2[3:] == clean1:
                return True
    
    return False

def is_same_book(google_title, google_authors, google_isbn_list, book_title, book_author, book_isbn):
    """
    判斷兩本書是否為同一本書（使用與搜尋結果相同的算法）
    
    參數:
        google_title: Google Books 的書名
        google_authors: Google Books 的作者列表
        google_isbn_list: Google Books 的 ISBN 列表
        book_title: 資料庫中的書名
        book_author: 資料庫中的作者
        book_isbn: 資料庫中的 ISBN
    
    返回:
        True 如果匹配，False 如果不匹配
    """
    # 標準化文字
    normalized_title = normalize_text_for_matching(google_title) if google_title else ""
    normalized_authors = [normalize_text_for_matching(author) for author in google_authors] if google_authors else []
    book_title_norm = normalize_text_for_matching(book_title) if book_title else ""
    book_author_norm = normalize_text_for_matching(book_author) if book_author else ""
    
    # 階段 1：ISBN 匹配（最準確，優先檢查）
    if google_isbn_list and book_isbn:
        for isbn in google_isbn_list:
            if match_isbn_for_matching(isbn, book_isbn):
                return True
    
    # 階段 2：書名相似度匹配
    title_similarity = 0.0
    if normalized_title and book_title_norm:
        title_similarity = calculate_similarity_for_matching(normalized_title, book_title_norm)
    
    # 階段 3：作者匹配
    author_match = False
    if normalized_authors and book_author_norm:
        for author in normalized_authors:
            if author:
                author_sim = calculate_similarity_for_matching(author, book_author_norm)
                if author_sim >= 0.6:
                    author_match = True
                    break
                # 完全包含匹配
                if author in book_author_norm or book_author_norm in author:
                    author_match = True
                    break
                # 處理多作者情況
                if ',' in book_author_norm:
                    authors_list = [a.strip() for a in book_author_norm.split(',')]
                    if author in authors_list:
                        author_match = True
                        break
                if ',' in author:
                    authors_list = [a.strip() for a in author.split(',')]
                    if book_author_norm in authors_list:
                        author_match = True
                        break
    
    # 階段 4：綜合判斷
    if title_similarity == 1.0:  # 書名完全匹配
        if author_match or not normalized_authors:
            return True
    elif title_similarity >= 0.85:  # 書名高度相似（>= 85%）
        if author_match:
            return True
    elif title_similarity >= 0.70:  # 書名中等相似（70-85%）
        # 需要更嚴格的作者匹配
        if normalized_authors and book_author_norm:
            for author in normalized_authors:
                if author:
                    author_sim = calculate_similarity_for_matching(author, book_author_norm)
                    if author_sim >= 0.75 or author == book_author_norm or book_author_norm == author:
                        return True
    
    return False

# ============================================================
# Firebase Storage 圖片上傳功能
# ============================================================

def compress_image(image_file, max_size=(1200, 1600), quality=85):
    """
    壓縮圖片以節省流量
    參數:
        image_file: Flask 的 FileStorage 對象
        max_size: 最大尺寸 (width, height)，預設 1200x1600
        quality: JPEG 品質 (1-100)，預設 85
    返回:
        壓縮後的圖片 bytes
    """
    try:
        # 讀取原始圖片
        image = Image.open(image_file)
        
        # 轉換為 RGB（如果是 RGBA 或其他格式）
        if image.mode in ('RGBA', 'LA', 'P'):
            # 創建白色背景
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
            image = background
        elif image.mode != 'RGB':
            image = image.convert('RGB')
        
        # 計算縮放比例，保持長寬比
        width, height = image.size
        max_width, max_height = max_size
        
        if width > max_width or height > max_height:
            # 計算縮放比例
            ratio = min(max_width / width, max_height / height)
            new_width = int(width * ratio)
            new_height = int(height * ratio)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # 將圖片轉換為 bytes
        output = io.BytesIO()
        image.save(output, format='JPEG', quality=quality, optimize=True)
        output.seek(0)
        
        return output.getvalue()
    except Exception as e:
        print(f"壓縮圖片時發生錯誤: {e}")
        import traceback
        traceback.print_exc()
        # 如果壓縮失敗，返回原始圖片
        image_file.seek(0)
        return image_file.read()

def upload_image_to_firebase_storage(image_file, user_email, image_type="front"):
    """
    上傳圖片到 Firebase Storage
    參數:
        image_file: Flask 的 FileStorage 對象
        user_email: 用戶 email
        image_type: 圖片類型 ("front" 或 "back")
    返回:
        圖片的公開 URL
    """
    try:
        # 獲取 Firebase Storage bucket（使用配置中的 bucket 名稱）
        bucket_name = "book-exchange-d4351.firebasestorage.app"
        bucket = storage.bucket(bucket_name)
        
        # 生成唯一檔名
        file_extension = os.path.splitext(image_file.filename)[1] if image_file.filename else '.jpg'
        if not file_extension or file_extension.lower() not in ['.jpg', '.jpeg', '.png', '.webp']:
            file_extension = '.jpg'
        
        # 使用用戶 email 和時間戳生成唯一檔名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_email = user_email.replace('@', '_at_').replace('.', '_')
        filename = f"books/{safe_email}/{timestamp}_{image_type}{file_extension}"
        
        # 壓縮圖片
        compressed_image = compress_image(image_file)
        
        # 創建 blob（Firebase Storage 的文件對象）
        blob = bucket.blob(filename)
        
        # 設置內容類型
        blob.content_type = 'image/jpeg'
        
        # 上傳圖片（使用壓縮後的數據）
        blob.upload_from_string(compressed_image, content_type='image/jpeg')
        
        # 設置為公開讀取（這樣才能在前端顯示）
        blob.make_public()
        
        # 返回公開 URL
        return blob.public_url
        
    except Exception as e:
        print(f"上傳圖片到 Firebase Storage 時發生錯誤: {e}")
        import traceback
        traceback.print_exc()
        raise

# API: 發送訊息
@app.route("/api/chat/<chat_id>/send", methods=["POST"])
def send_message(chat_id):
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        current_user = session["user"]
        data = request.json
        content = data.get("content", "").strip()
        
        if not content:
            return jsonify({"success": False, "error": "訊息內容不能為空"}), 400
        
        # 檢查聊天室是否存在且用戶是參與者
        chat_ref = db.collection("chats").document(chat_id)
        chat_doc = chat_ref.get()
        if not chat_doc.exists:
            return jsonify({"success": False, "error": "聊天室不存在"}), 404
        
        chat_dict = chat_doc.to_dict()
        participants = chat_dict.get("participants", [])
        if current_user not in participants:
            return jsonify({"success": False, "error": "無權限"}), 403
        
        # 獲取可選的書籍資訊（如果從特定書籍頁面發送）
        book_id = data.get("book_id", "")
        book_title = ""
        book_author = ""
        book_image = ""
        if book_id:
            try:
                book_ref = db.collection("books").document(book_id)
                book_doc = book_ref.get()
                if book_doc.exists:
                    book_dict = book_doc.to_dict()
                    book_title = book_dict.get("title", "")
                    book_author = book_dict.get("author", "")
                    book_image = book_dict.get("front_image", "")
            except Exception as book_error:
                print(f"獲取書籍資訊時發生錯誤: {book_error}")
        
        # 檢查這是否是第一條訊息（如果提供了book_id且聊天室沒有訊息）
        is_first_message = False
        if book_id:
            try:
                messages_ref = db.collection("messages")
                existing_messages = messages_ref.where("chat_id", "==", chat_id).limit(1).stream()
                existing_messages_list = list(existing_messages)
                if len(existing_messages_list) == 0:
                    is_first_message = True
            except Exception as check_error:
                print(f"檢查是否為第一條訊息時發生錯誤: {check_error}")
        
        # 如果是第一條訊息且有書籍資訊，先發送書籍資訊卡片
        if is_first_message and book_id and book_title:
            try:
                book_info_message = {
                    "chat_id": chat_id,
                    "sender_email": current_user,
                    "content": "",  # 書籍資訊卡片不需要文字內容
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "read": False,
                    "book_id": book_id,
                    "book_title": book_title,
                    "book_author": book_author,
                    "book_image": book_image,
                    "is_book_info": True  # 標記這是書籍資訊卡片
                }
                book_info_ref = db.collection("messages").document()
                book_info_ref.set(book_info_message)
                print(f"書籍資訊卡片已發送: book_id={book_id}, book_title={book_title}")
            except Exception as book_info_error:
                print(f"發送書籍資訊卡片時發生錯誤: {book_info_error}")
                # 即使發送書籍資訊卡片失敗，繼續發送主要訊息
        
        # 創建訊息（不包含書籍資訊，避免重複顯示）
        message_data = {
            "chat_id": chat_id,
            "sender_email": current_user,
            "content": content,
            "created_at": firestore.SERVER_TIMESTAMP,
            "read": False
        }
        
        message_ref = db.collection("messages").document()
        
        # 寫入訊息到 Firestore
        try:
            message_ref.set(message_data)
            print(f"訊息已寫入 Firestore: message_id={message_ref.id}, chat_id={chat_id}, sender={current_user}, content={content[:50]}")
        except Exception as write_error:
            print(f"寫入訊息到 Firestore 時發生錯誤: {write_error}")
            import traceback
            traceback.print_exc()
            return jsonify({"success": False, "error": f"儲存訊息失敗: {str(write_error)}"}), 500
        
        # 更新聊天室的最後訊息資訊
        try:
            chat_ref.update({
                "last_message": content,
                "last_message_time": firestore.SERVER_TIMESTAMP,
                "last_message_sender": current_user
            })
            print(f"聊天室已更新: chat_id={chat_id}, last_message={content[:50]}")
        except Exception as update_error:
            print(f"更新聊天室時發生錯誤: {update_error}")
            # 即使更新聊天室失敗，訊息已經儲存，所以繼續執行
        
        # 等待一小段時間確保寫入完成，然後重新讀取訊息以獲取實際的時間戳記
        import time
        time.sleep(0.1)  # 等待 100ms 確保 Firestore 寫入完成
        
        message_doc = message_ref.get()
        if message_doc.exists:
            message_dict = message_doc.to_dict()
            message_dict["id"] = message_ref.id
            
            # 處理時間戳記用於返回（轉換為 UTC+8）
            if "created_at" in message_dict and message_dict["created_at"]:
                try:
                    dt = None
                    if hasattr(message_dict["created_at"], "strftime"):
                        dt = message_dict["created_at"]
                    elif hasattr(message_dict["created_at"], "timestamp"):
                        dt = message_dict["created_at"].to_datetime()
                    
                    if dt:
                        # 轉換為 UTC+8
                        dt_utc8 = convert_to_utc8(dt)
                        message_dict["created_at"] = dt_utc8.strftime("%Y-%m-%d %H:%M")
                    else:
                        message_dict["created_at"] = str(message_dict["created_at"])[:16]
                except:
                    message_dict["created_at"] = str(message_dict["created_at"])[:16] if message_dict["created_at"] else ""
            else:
                message_dict["created_at"] = ""
            
            return jsonify({"success": True, "message": message_dict})
        else:
            # 如果讀取失敗，返回基本信息
            return jsonify({
                "success": True,
                "message": {
                    "id": message_ref.id,
                    "chat_id": chat_id,
                    "sender_email": current_user,
                    "content": content,
                    "created_at": "",
                    "read": False
                }
            })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

# API: 獲取聊天訊息
@app.route("/api/chat/<chat_id>/messages", methods=["GET"])
def get_messages(chat_id):
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        current_user = session["user"]
        
        # 檢查聊天室是否存在且用戶是參與者
        chat_ref = db.collection("chats").document(chat_id)
        chat_doc = chat_ref.get()
        if not chat_doc.exists:
            return jsonify({"success": False, "error": "聊天室不存在"}), 404
        
        chat_dict = chat_doc.to_dict()
        participants = chat_dict.get("participants", [])
        if current_user not in participants:
            return jsonify({"success": False, "error": "無權限"}), 403
        
        # 獲取訊息列表並標記未讀訊息為已讀
        messages_ref = db.collection("messages")
        try:
            # 先嘗試使用 order_by 查詢
            try:
                messages_query = messages_ref.where("chat_id", "==", chat_id).order_by("created_at", direction=firestore.Query.ASCENDING).limit(100)
                # 立即轉換為列表以觸發查詢和異常（如果索引不存在）
                messages_docs = list(messages_query.stream())
                print(f"API: 使用 order_by 查詢成功，找到 {len(messages_docs)} 條訊息")
            except Exception as order_error:
                # 如果 order_by 失敗（可能是缺少索引），使用簡單查詢然後在內存中排序
                print(f"API: 使用 order_by 查詢失敗，改用簡單查詢: {order_error}")
                messages_query = messages_ref.where("chat_id", "==", chat_id).limit(100)
                messages_docs = list(messages_query.stream())
                # 在內存中排序
                all_messages = []
                for msg_doc in messages_docs:
                    msg_dict = msg_doc.to_dict()
                    msg_dict["id"] = msg_doc.id
                    all_messages.append(msg_dict)
                # 按 created_at 排序（使用正確的排序函數處理 Timestamp）
                all_messages.sort(key=get_message_sort_key)
                messages_docs = all_messages
                print(f"API: 使用內存排序，共 {len(all_messages)} 條訊息")
            
            # 標記未讀訊息為已讀（發送者不是當前用戶且未讀的訊息）
            unread_count = 0
            for msg_doc in messages_docs:
                # 處理兩種情況：DocumentSnapshot 或 dict
                if hasattr(msg_doc, 'to_dict'):
                    msg_dict = msg_doc.to_dict()
                    msg_id = msg_doc.id
                else:
                    msg_dict = msg_doc
                    msg_id = msg_dict.get("id", "")
                
                sender = msg_dict.get("sender_email", "")
                read_status = msg_dict.get("read", False)
                
                # 如果是別人發送的未讀訊息，標記為已讀
                if sender != current_user and not read_status:
                    try:
                        if hasattr(msg_doc, 'reference'):
                            # DocumentSnapshot 情況
                            msg_doc.reference.update({"read": True})
                        elif msg_id:
                            # dict 情況，需要重新獲取文檔引用
                            msg_ref = messages_ref.document(msg_id)
                            msg_ref.update({"read": True})
                        unread_count += 1
                    except Exception as update_error:
                        print(f"API: 標記訊息為已讀時發生錯誤: {update_error}")
            
            if unread_count > 0:
                print(f"API: 已標記 {unread_count} 條訊息為已讀，chat_id={chat_id}")
            
            messages = []
            # 處理訊息
            for msg_doc in messages_docs:
                # 處理兩種情況：DocumentSnapshot 或 dict
                if hasattr(msg_doc, 'to_dict'):
                    msg_dict = msg_doc.to_dict()
                    msg_dict["id"] = msg_doc.id
                else:
                    msg_dict = msg_doc
                
                # 處理時間戳記（轉換為 UTC+8）
                if "created_at" in msg_dict and msg_dict["created_at"]:
                    try:
                        dt = None
                        if hasattr(msg_dict["created_at"], "strftime"):
                            dt = msg_dict["created_at"]
                        elif hasattr(msg_dict["created_at"], "timestamp"):
                            dt = msg_dict["created_at"].to_datetime()
                        
                        if dt:
                            # 轉換為 UTC+8
                            dt_utc8 = convert_to_utc8(dt)
                            msg_dict["created_at"] = dt_utc8.strftime("%Y-%m-%d %H:%M")
                        else:
                            msg_dict["created_at"] = str(msg_dict["created_at"])[:16]
                    except Exception as time_error:
                        print(f"API: 處理時間戳記時發生錯誤: {time_error}")
                        msg_dict["created_at"] = str(msg_dict["created_at"])[:16] if msg_dict["created_at"] else ""
                else:
                    msg_dict["created_at"] = ""
                
                messages.append(msg_dict)
            
            print(f"API: 成功獲取 {len(messages)} 條訊息，chat_id={chat_id}")
            return jsonify({"success": True, "messages": messages})
        except Exception as query_error:
            import traceback
            print(f"API: 查詢訊息時發生錯誤：{query_error}")
            traceback.print_exc()
            return jsonify({"success": False, "error": f"查詢訊息失敗: {str(query_error)}"}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

# API: 獲取當前用戶提供的書籍清單（用於交易提醒，雙方都可以使用）
@app.route("/api/my-books", methods=["GET"])
def get_my_books():
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        current_user = session["user"]
        
        # 獲取當前用戶提供的書籍
        books_ref = db.collection("books")
        books_query = books_ref.where("seller_email", "==", current_user).where("status", "==", "available").limit(50)
        books = books_query.stream()
        
        books_list = []
        for book in books:
            book_dict = book.to_dict()
            book_dict["id"] = book.id
            books_list.append({
                "id": book_dict["id"],
                "title": book_dict.get("title", ""),
                "author": book_dict.get("author", "")
            })
        
        return jsonify({"success": True, "books": books_list})
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"獲取用戶書籍清單時發生錯誤：{e}")
        return jsonify({"success": False, "error": str(e)}), 500

# API: 獲取交易提醒
@app.route("/api/chat/<chat_id>/transaction_reminder", methods=["GET"])
def get_transaction_reminder(chat_id):
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        current_user = session["user"]
        
        # 檢查聊天室是否存在且用戶是參與者
        chat_ref = db.collection("chats").document(chat_id)
        chat_doc = chat_ref.get()
        if not chat_doc.exists:
            return jsonify({"success": False, "error": "聊天室不存在"}), 404
        
        chat_dict = chat_doc.to_dict()
        participants = chat_dict.get("participants", [])
        if current_user not in participants:
            return jsonify({"success": False, "error": "無權限"}), 403
        
        # 獲取交易提醒（包括已完成的，用於顯示評價提示）
        reminders_ref = db.collection("transaction_reminders")
        # 先查詢未完成的交易提醒
        reminders_query = reminders_ref.where("chat_id", "==", chat_id).where("completed", "==", False).limit(1)
        reminders = list(reminders_query.stream())
        # 如果沒有未完成的，查詢已完成的（用於顯示評價提示）
        if not reminders:
            completed_query = reminders_ref.where("chat_id", "==", chat_id).where("completed", "==", True).order_by("completed_at", direction=firestore.Query.DESCENDING).limit(1)
            try:
                reminders = list(completed_query.stream())
            except Exception as order_error:
                # 如果 order_by 失敗，使用簡單查詢
                completed_query = reminders_ref.where("chat_id", "==", chat_id).where("completed", "==", True).limit(1)
                reminders = list(completed_query.stream())
                # 在內存中按 completed_at 排序
                if reminders:
                    def get_reminder_sort_key(reminder_doc):
                        reminder_dict = reminder_doc.to_dict()
                        completed_at = reminder_dict.get("completed_at")
                        if not completed_at:
                            return datetime.min
                        if hasattr(completed_at, "strftime"):
                            return completed_at
                        elif hasattr(completed_at, "timestamp"):
                            try:
                                return completed_at.to_datetime()
                            except:
                                return datetime.min
                        else:
                            return datetime.min
                    reminders.sort(key=get_reminder_sort_key, reverse=True)
                    reminders = reminders[:1]  # 只取最新的一個
        
        if reminders:
            reminder_dict = reminders[0].to_dict()
            reminder_dict["id"] = reminders[0].id
            
            # 處理時間戳記（轉換為 UTC+8）
            if "transaction_datetime" in reminder_dict and reminder_dict["transaction_datetime"]:
                try:
                    dt = None
                    if hasattr(reminder_dict["transaction_datetime"], "strftime"):
                        dt = reminder_dict["transaction_datetime"]
                    elif hasattr(reminder_dict["transaction_datetime"], "timestamp"):
                        dt = reminder_dict["transaction_datetime"].to_datetime()
                    if dt:
                        dt_utc8 = convert_to_utc8(dt)
                        reminder_dict["transaction_datetime"] = dt_utc8.isoformat()
                except Exception as time_error:
                    print(f"處理交易提醒時間戳記時發生錯誤: {time_error}")
            
            return jsonify({"success": True, "reminder": reminder_dict})
        else:
            return jsonify({"success": True, "reminder": None})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

# API: 創建或更新交易提醒（雙方都可以創建，記錄 created_by）
@app.route("/api/chat/<chat_id>/transaction_reminder", methods=["POST"])
def create_or_update_transaction_reminder(chat_id):
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        current_user = session["user"]
        data = request.json
        
        # 檢查聊天室是否存在且用戶是參與者
        chat_ref = db.collection("chats").document(chat_id)
        chat_doc = chat_ref.get()
        if not chat_doc.exists:
            return jsonify({"success": False, "error": "聊天室不存在"}), 404
        
        chat_dict = chat_doc.to_dict()
        participants = chat_dict.get("participants", [])
        if current_user not in participants:
            return jsonify({"success": False, "error": "無權限"}), 403
        
        # 獲取書籍資訊
        book_id = data.get("book_id", "").strip()
        if not book_id:
            return jsonify({"success": False, "error": "請選擇書籍"}), 400
        
        book_ref = db.collection("books").document(book_id)
        book_doc = book_ref.get()
        if not book_doc.exists:
            return jsonify({"success": False, "error": "書籍不存在"}), 404
        
        book_dict = book_doc.to_dict()
        book_title = book_dict.get("title", "")
        
        # 處理交易時間（將本地時間轉換為 UTC+8 的 datetime）
        transaction_datetime_str = data.get("transaction_datetime", "").strip()
        if not transaction_datetime_str:
            return jsonify({"success": False, "error": "請選擇交易時間"}), 400
        
        try:
            # datetime-local 輸入格式：YYYY-MM-DDTHH:mm
            # 假設這是 UTC+8 時間，需要轉換為 UTC 存儲
            dt_local = datetime.strptime(transaction_datetime_str, "%Y-%m-%dT%H:%M")
            # 將本地時間視為 UTC+8，轉換為 UTC
            dt_utc8 = dt_local.replace(tzinfo=timezone(timedelta(hours=8)))
            dt_utc = dt_utc8.astimezone(timezone.utc)
        except Exception as dt_error:
            print(f"解析交易時間時發生錯誤: {dt_error}")
            return jsonify({"success": False, "error": "交易時間格式錯誤"}), 400
        
        transaction_location = data.get("transaction_location", "").strip()
        if not transaction_location:
            return jsonify({"success": False, "error": "請輸入交易地點"}), 400
        
        notes = data.get("notes", "").strip()
        email_notification = data.get("email_notification", False)
        
        # 檢查是否已存在交易提醒
        reminders_ref = db.collection("transaction_reminders")
        existing_reminders = reminders_ref.where("chat_id", "==", chat_id).where("completed", "==", False).limit(1).stream()
        existing_reminder_list = list(existing_reminders)
        
        reminder_data = {
            "chat_id": chat_id,
            "book_id": book_id,
            "book_title": book_title,
            "transaction_datetime": dt_utc,  # 存儲為 UTC
            "transaction_location": transaction_location,
            "notes": notes,
            "email_notification": email_notification,
            "created_by": current_user,  # 記錄是誰填寫的（提供書籍的人）
            "completed": False,
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP
        }
        
        if existing_reminder_list:
            # 更新現有提醒（保留原有的 created_by）
            reminder_ref = reminders_ref.document(existing_reminder_list[0].id)
            existing_dict = existing_reminder_list[0].to_dict()
            # 保留原有的 created_by（重要：不允許更改填寫者）
            original_created_by = existing_dict.get("created_by", current_user)
            reminder_data["created_by"] = original_created_by
            reminder_data["updated_at"] = firestore.SERVER_TIMESTAMP
            reminder_ref.update(reminder_data)
            reminder_id = existing_reminder_list[0].id
        else:
            # 創建新提醒
            reminder_ref = reminders_ref.document()
            reminder_ref.set(reminder_data)
            reminder_id = reminder_ref.id
        
        # 重新從 Firestore 讀取數據以獲取實際的時間戳記
        updated_reminder_ref = reminders_ref.document(reminder_id)
        updated_reminder_doc = updated_reminder_ref.get()
        if updated_reminder_doc.exists:
            updated_reminder_dict = updated_reminder_doc.to_dict()
            updated_reminder_dict["id"] = reminder_id
            
            # 處理時間戳記（轉換為 UTC+8）
            if "transaction_datetime" in updated_reminder_dict and updated_reminder_dict["transaction_datetime"]:
                try:
                    dt = None
                    if hasattr(updated_reminder_dict["transaction_datetime"], "strftime"):
                        dt = updated_reminder_dict["transaction_datetime"]
                    elif hasattr(updated_reminder_dict["transaction_datetime"], "timestamp"):
                        dt = updated_reminder_dict["transaction_datetime"].to_datetime()
                    if dt:
                        dt_utc8 = convert_to_utc8(dt)
                        updated_reminder_dict["transaction_datetime"] = dt_utc8.isoformat()
                except Exception as time_error:
                    print(f"處理交易提醒時間戳記時發生錯誤: {time_error}")
                    updated_reminder_dict["transaction_datetime"] = dt_utc8.isoformat()
            
            # 處理 created_at 和 updated_at（轉換為字符串）
            for time_field in ["created_at", "updated_at"]:
                if time_field in updated_reminder_dict and updated_reminder_dict[time_field]:
                    try:
                        dt = None
                        if hasattr(updated_reminder_dict[time_field], "strftime"):
                            dt = updated_reminder_dict[time_field]
                        elif hasattr(updated_reminder_dict[time_field], "timestamp"):
                            dt = updated_reminder_dict[time_field].to_datetime()
                        if dt:
                            dt_utc8 = convert_to_utc8(dt)
                            updated_reminder_dict[time_field] = dt_utc8.isoformat()
                        else:
                            updated_reminder_dict[time_field] = ""
                    except Exception as time_error:
                        print(f"處理 {time_field} 時間戳記時發生錯誤: {time_error}")
                        updated_reminder_dict[time_field] = ""
            
            return jsonify({"success": True, "reminder": updated_reminder_dict})
        else:
            # 如果讀取失敗，返回基本信息（不包含 SERVER_TIMESTAMP）
            return_data = {
                "id": reminder_id,
                "chat_id": chat_id,
                "book_id": book_id,
                "book_title": book_title,
                "transaction_datetime": dt_utc8.isoformat(),
                "transaction_location": transaction_location,
                "notes": notes,
                "email_notification": email_notification,
                "created_by": reminder_data.get("created_by", current_user),
                "completed": False
            }
            return jsonify({"success": True, "reminder": return_data})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

# API: 獲取未讀訊息總數
@app.route("/api/unread-messages/count", methods=["GET"])
def get_unread_messages_count():
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        current_user = session["user"]
        
        # 獲取當前用戶的所有聊天室
        chats_ref = db.collection("chats")
        chats_query = chats_ref.where("participants", "array_contains", current_user).limit(50)
        chats = list(chats_query.stream())
        
        total_unread = 0
        
        # 遍歷所有聊天室，計算未讀訊息
        for chat_doc in chats:
            chat_id = chat_doc.id
            try:
                messages_ref = db.collection("messages")
                # 查詢該聊天室中未讀的訊息（發送者不是當前用戶且未讀）
                unread_messages_query = messages_ref.where("chat_id", "==", chat_id)\
                                                    .where("sender_email", "!=", current_user)\
                                                    .where("read", "==", False)\
                                                    .limit(100)
                unread_messages = list(unread_messages_query.stream())
                total_unread += len(unread_messages)
            except Exception as msg_error:
                # 如果查詢失敗（可能是缺少索引），使用簡單查詢
                try:
                    messages_ref = db.collection("messages")
                    all_messages = messages_ref.where("chat_id", "==", chat_id).limit(100).stream()
                    for msg_doc in all_messages:
                        msg_dict = msg_doc.to_dict()
                        sender = msg_dict.get("sender_email", "")
                        read_status = msg_dict.get("read", False)
                        if sender != current_user and not read_status:
                            total_unread += 1
                except:
                    pass
        
        return jsonify({"success": True, "unread_count": total_unread})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

# API: 完成交易（修改版，返回 transaction_id）
@app.route("/api/chat/<chat_id>/transaction_reminder/complete", methods=["POST"])
def complete_transaction(chat_id):
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        current_user = session["user"]
        data = request.json
        book_id = data.get("book_id", "").strip()
        
        if not book_id:
            return jsonify({"success": False, "error": "缺少書籍ID"}), 400
        
        # 檢查聊天室是否存在且用戶是參與者
        chat_ref = db.collection("chats").document(chat_id)
        chat_doc = chat_ref.get()
        if not chat_doc.exists:
            return jsonify({"success": False, "error": "聊天室不存在"}), 404
        
        chat_dict = chat_doc.to_dict()
        participants = chat_dict.get("participants", [])
        if current_user not in participants:
            return jsonify({"success": False, "error": "無權限"}), 403
        
        # 獲取交易提醒
        reminders_ref = db.collection("transaction_reminders")
        reminders_query = reminders_ref.where("chat_id", "==", chat_id).where("completed", "==", False).limit(1)
        reminders = list(reminders_query.stream())
        
        if not reminders:
            return jsonify({"success": False, "error": "找不到交易提醒"}), 404
        
        reminder = reminders[0]
        reminder_dict = reminder.to_dict()
        
        # 驗證書籍ID是否匹配
        if reminder_dict.get("book_id") != book_id:
            return jsonify({"success": False, "error": "書籍ID不匹配"}), 400
        
        # 驗證當前用戶是否是賣家
        book_ref = db.collection("books").document(book_id)
        book_doc = book_ref.get()
        if not book_doc.exists:
            return jsonify({"success": False, "error": "書籍不存在"}), 404
        
        book_dict = book_doc.to_dict()
        if book_dict.get("seller_email") != current_user:
            return jsonify({"success": False, "error": "只有賣家可以完成交易"}), 403
        
        # 標記交易提醒為已完成
        transaction_id = reminder.id
        reminder.reference.update({
            "completed": True,
            "completed_at": firestore.SERVER_TIMESTAMP,
            "completed_by": current_user
        })
        
        # 刪除書籍（從資料庫中刪除）
        evaluation_id = book_dict.get("evaluation_id", "")
        if evaluation_id:
            try:
                eval_ref = db.collection("evaluations").document(evaluation_id)
                if eval_ref.get().exists:
                    eval_ref.delete()
            except Exception as eval_error:
                print(f"刪除評價時發生錯誤: {eval_error}")
        
        # 刪除書籍圖片
        front_image = book_dict.get("front_image", "")
        back_image = book_dict.get("back_image", "")
        
        for image_url in [front_image, back_image]:
            if image_url and image_url.startswith("https://"):
                try:
                    bucket = storage.bucket()
                    if "firebasestorage.googleapis.com" in image_url:
                        path_start = image_url.find("/o/") + 3
                        path_end = image_url.find("?")
                        if path_end == -1:
                            path_end = len(image_url)
                        file_path = image_url[path_start:path_end]
                        file_path = file_path.replace("%2F", "/")
                        blob = bucket.blob(file_path)
                        if blob.exists():
                            blob.delete()
                except Exception as img_error:
                    print(f"刪除圖片時發生錯誤: {img_error}")
        
        # 刪除收藏記錄
        try:
            favorites_ref = db.collection("favorites")
            favorites_query = favorites_ref.where("item_id", "==", book_id).where("item_type", "==", "book")
            for favorite in favorites_query.stream():
                favorite.reference.delete()
        except Exception as fav_error:
            print(f"刪除收藏記錄時發生錯誤: {fav_error}")
        
        # 刪除書籍
        book_ref.delete()
        
        return jsonify({"success": True, "message": "交易已完成，書籍已刪除", "transaction_id": transaction_id})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

# API: 獲取交易評價狀態
@app.route("/api/transaction/<transaction_id>/evaluation/status", methods=["GET"])
def get_transaction_evaluation_status(transaction_id):
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        current_user = session["user"]
        
        # 檢查交易是否存在
        reminder_ref = db.collection("transaction_reminders").document(transaction_id)
        reminder_doc = reminder_ref.get()
        if not reminder_doc.exists:
            return jsonify({"success": False, "error": "交易不存在"}), 404
        
        reminder_dict = reminder_doc.to_dict()
        if not reminder_dict.get("completed"):
            return jsonify({"success": False, "error": "交易尚未完成"}), 400
        
        # 獲取聊天室參與者
        chat_id = reminder_dict.get("chat_id", "")
        participants = []
        if chat_id:
            try:
                chat_ref = db.collection("chats").document(chat_id)
                chat_doc = chat_ref.get()
                if chat_doc.exists:
                    chat_dict = chat_doc.to_dict()
                    participants = chat_dict.get("participants", [])
                    # 去重
                    participants = list(set(participants))
            except Exception as chat_error:
                print(f"獲取聊天室參與者時發生錯誤: {chat_error}")
        
        # 查詢當前用戶的評價
        evaluations_ref = db.collection("transaction_evaluations")
        eval_query = evaluations_ref.where("transaction_id", "==", transaction_id)\
                                   .where("evaluator_email", "==", current_user).limit(1)
        eval_docs = list(eval_query.stream())
        
        has_evaluated = len(eval_docs) > 0
        
        # 檢查雙方是否都填寫了評價
        all_evaluated = False
        if len(participants) == 2:
            # 查詢所有參與者的評價
            all_eval_query = evaluations_ref.where("transaction_id", "==", transaction_id)
            all_eval_docs = list(all_eval_query.stream())
            evaluated_emails = set()
            for eval_doc in all_eval_docs:
                eval_dict = eval_doc.to_dict()
                evaluator_email = eval_dict.get("evaluator_email", "")
                if evaluator_email:
                    evaluated_emails.add(evaluator_email)
            # 檢查是否所有參與者都填寫了評價
            all_evaluated = len(evaluated_emails) == len(participants) and all(p in evaluated_emails for p in participants)
        
        return jsonify({
            "success": True,
            "has_evaluated": has_evaluated,
            "evaluation_id": eval_docs[0].id if has_evaluated else None,
            "all_evaluated": all_evaluated
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

# API: 提交交易評價
@app.route("/api/transaction/<transaction_id>/evaluation", methods=["POST"])
def submit_transaction_evaluation(transaction_id):
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        current_user = session["user"]
        data = request.json
        
        # 檢查交易是否存在
        reminder_ref = db.collection("transaction_reminders").document(transaction_id)
        reminder_doc = reminder_ref.get()
        if not reminder_doc.exists:
            return jsonify({"success": False, "error": "交易不存在"}), 404
        
        reminder_dict = reminder_doc.to_dict()
        if not reminder_dict.get("completed"):
            return jsonify({"success": False, "error": "交易尚未完成"}), 400
        
        # 獲取對方用戶
        chat_id = reminder_dict.get("chat_id", "")
        chat_ref = db.collection("chats").document(chat_id)
        chat_doc = chat_ref.get()
        if not chat_doc.exists:
            return jsonify({"success": False, "error": "聊天室不存在"}), 404
        
        chat_dict = chat_doc.to_dict()
        participants = chat_dict.get("participants", [])
        if current_user not in participants:
            return jsonify({"success": False, "error": "無權限"}), 403
        
        # 找到對方用戶
        other_user = participants[0] if participants[1] == current_user else participants[1]
        
        # 檢查是否已經評價過
        evaluations_ref = db.collection("transaction_evaluations")
        existing_eval = evaluations_ref.where("transaction_id", "==", transaction_id)\
                                      .where("evaluator_email", "==", current_user).limit(1).stream()
        existing_list = list(existing_eval)
        
        evaluation_data = {
            "transaction_id": transaction_id,
            "evaluator_email": current_user,
            "evaluated_email": other_user,
            "rating": int(data.get("rating", 0)),
            "on_time": data.get("on_time", False),
            "correct_item": data.get("correct_item", False),
            "notes": data.get("notes", "").strip(),
            "created_at": firestore.SERVER_TIMESTAMP
        }
        
        if existing_list:
            # 更新現有評價
            eval_ref = evaluations_ref.document(existing_list[0].id)
            evaluation_data["updated_at"] = firestore.SERVER_TIMESTAMP
            eval_ref.update(evaluation_data)
            eval_id = existing_list[0].id
        else:
            # 創建新評價
            eval_ref = evaluations_ref.document()
            eval_ref.set(evaluation_data)
            eval_id = eval_ref.id
        
        # 更新用戶的評價統計（計算平均分數）
        try:
            # 獲取該用戶收到的所有評價
            all_evals = evaluations_ref.where("evaluated_email", "==", other_user).stream()
            ratings = []
            for eval_doc in all_evals:
                eval_dict = eval_doc.to_dict()
                rating = eval_dict.get("rating", 0)
                if rating > 0:
                    ratings.append(rating)
            
            avg_rating = sum(ratings) / len(ratings) if ratings else 0
            
            # 更新用戶文檔（如果有的話）
            users_ref = db.collection("users")
            user_query = users_ref.where("email", "==", other_user).limit(1)
            user_docs = list(user_query.stream())
            if user_docs:
                user_docs[0].reference.update({
                    "transaction_rating": avg_rating,
                    "transaction_rating_count": len(ratings),
                    "updated_at": firestore.SERVER_TIMESTAMP
                })
        except Exception as update_error:
            print(f"更新用戶評價統計時發生錯誤: {update_error}")
        
        return jsonify({"success": True, "evaluation_id": eval_id})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

# 檢查是否在 Firebase Functions 環境中
if os.getenv('FIREBASE_FUNCTIONS') != '1':
    # 本地開發模式
    if __name__ == "__main__":
        # 允許從其他設備訪問（手機測試）
        # host='0.0.0.0' 表示監聽所有網路介面
        # 在手機瀏覽器中訪問: http://你的電腦IP:5000
        app.run(host='0.0.0.0', port=5000, debug=True)