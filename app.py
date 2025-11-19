import firebase_admin
import pyrebase
from firebase_admin import credentials, firestore, storage
from flask import Flask, render_template, request, redirect, session,jsonify
from dotenv import load_dotenv
import os
import datetime
import requests
from PIL import Image
import io
import uuid

app = Flask(__name__)
app.secret_key = "supersecretkey"

# 初始化 Firebase Admin
cred = credentials.Certificate("firebase_config.json")
firebase_admin.initialize_app(cred)
db = firestore.client()
load_dotenv()

firebase_api_key = os.getenv("FIREBASE_API_KEY")
firebase_auth_domain = os.getenv("FIREBASE_AUTH_DOMAIN")

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
    # 處理時間戳記
    if "created_at" in book_dict and book_dict["created_at"]:
        try:
            if hasattr(book_dict["created_at"], "strftime"):
                book_dict["created_at"] = book_dict["created_at"].strftime("%Y-%m-%d %H:%M:%S")
                book_dict["created_at_timestamp"] = book_dict["created_at"]
            elif hasattr(book_dict["created_at"], "timestamp"):
                from datetime import datetime
                dt = book_dict["created_at"].to_datetime()
                book_dict["created_at"] = dt.strftime("%Y-%m-%d %H:%M:%S")
                book_dict["created_at_timestamp"] = dt
            else:
                book_dict["created_at"] = str(book_dict["created_at"])
                book_dict["created_at_timestamp"] = book_dict["created_at"]
        except:
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

# 收藏書籍
@app.route("/api/favorite/<book_id>", methods=["POST"])
def add_favorite(book_id):
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        current_user = session["user"]
        
        # 檢查書籍是否存在
        book_ref = db.collection("books").document(book_id)
        book_doc = book_ref.get()
        if not book_doc.exists:
            return jsonify({"success": False, "error": "書籍不存在"}), 404
        
        # 檢查是否已經收藏
        favorites_ref = db.collection("favorites")
        favorites_query = favorites_ref.where("user_email", "==", current_user).where("book_id", "==", book_id).limit(1)
        existing = list(favorites_query.stream())
        
        if existing:
            return jsonify({"success": True, "message": "已經收藏"})
        
        # 添加收藏
        favorite_data = {
            "user_email": current_user,
            "book_id": book_id,
            "created_at": firestore.SERVER_TIMESTAMP
        }
        favorites_ref.add(favorite_data)
        
        return jsonify({"success": True, "message": "收藏成功"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

# 取消收藏
@app.route("/api/favorite/<book_id>", methods=["DELETE"])
def remove_favorite(book_id):
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        current_user = session["user"]
        
        # 查找並刪除收藏
        favorites_ref = db.collection("favorites")
        favorites_query = favorites_ref.where("user_email", "==", current_user).where("book_id", "==", book_id).limit(1)
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
@app.route("/api/favorite/<book_id>/check", methods=["GET"])
def check_favorite(book_id):
    if "user" not in session:
        return jsonify({"success": False, "is_favorited": False}), 401
    
    try:
        current_user = session["user"]
        favorites_ref = db.collection("favorites")
        favorites_query = favorites_ref.where("user_email", "==", current_user).where("book_id", "==", book_id).limit(1)
        favorites = list(favorites_query.stream())
        
        return jsonify({"success": True, "is_favorited": len(favorites) > 0})
    except Exception as e:
        return jsonify({"success": False, "is_favorited": False}), 500


# 註冊
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        std_num = request.form.get("std_num", "").strip()
        password = request.form.get("password", "")
        password_check = request.form.get("password-check", "")

        # 驗證輸入
        if not std_num:
            return render_template("register.html", error="請輸入學號")
        
        if not password:
            return render_template("register.html", error="請輸入密碼")
        
        if password != password_check:
            return render_template("register.html", error="兩次輸入的密碼不一致")
        
        # 驗證密碼規則
        if len(password) < 6:
            return render_template("register.html", error="密碼長度至少6位")
        
        if not any(c.isupper() for c in password):
            return render_template("register.html", error="密碼至少包含一個大寫字母")
        
        if not any(c.islower() for c in password):
            return render_template("register.html", error="密碼至少包含一個小寫字母")

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

            return render_template("register.html", email=True)
        except Exception as e:
            import traceback
            error_msg = str(e)
            print(f"Registration Error: {error_msg}")
            traceback.print_exc()
            
            # 提供更詳細的錯誤訊息
            if "EMAIL_EXISTS" in error_msg or "email-already-exists" in error_msg.lower():
                return render_template("register.html", error="該學號已被註冊，請使用其他學號。")
            elif "INVALID_EMAIL" in error_msg or "invalid-email" in error_msg.lower():
                return render_template("register.html", error="電子郵件格式無效。")
            elif "WEAK_PASSWORD" in error_msg or "weak-password" in error_msg.lower():
                return render_template("register.html", error="密碼強度不足，請使用更強的密碼。")
            else:
                return render_template("register.html", error=f"註冊失敗：{error_msg}")

    return render_template("register.html")


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
        
        # 檢查是查看自己還是其他人
        is_own_profile = (view_user == current_user)
        
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
                    
                    # 處理時間戳記（用於排序）
                    if "created_at" in book_dict and book_dict["created_at"]:
                        try:
                            if hasattr(book_dict["created_at"], "strftime"):
                                created_at_str = book_dict["created_at"].strftime("%Y-%m-%d")
                                created_at_for_sort = book_dict["created_at"]
                            elif hasattr(book_dict["created_at"], "timestamp"):
                                # Firestore Timestamp 物件
                                dt = book_dict["created_at"].to_datetime()
                                created_at_str = dt.strftime("%Y-%m-%d")
                                created_at_for_sort = dt
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
        
        # 計算用戶平均評分（基於用戶所有書籍的評價）
        ratings = []
        for book in provided_books:
            if book.get("rating", 0) > 0:
                ratings.append(book.get("rating", 0))
        
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
        else:
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
                    
                    # 處理時間戳記（用於排序）
                    if "created_at" in eval_dict and eval_dict["created_at"]:
                        try:
                            if hasattr(eval_dict["created_at"], "strftime"):
                                created_at_str = eval_dict["created_at"].strftime("%Y-%m-%d")
                                created_at_for_sort = eval_dict["created_at"]
                            elif hasattr(eval_dict["created_at"], "timestamp"):
                                # Firestore Timestamp 物件
                                dt = eval_dict["created_at"].to_datetime()
                                created_at_str = dt.strftime("%Y-%m-%d")
                                created_at_for_sort = dt
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
                
                # 處理時間戳記（用於排序）
                if "created_at" in wanted_dict and wanted_dict["created_at"]:
                    try:
                        if hasattr(wanted_dict["created_at"], "strftime"):
                            created_at_str = wanted_dict["created_at"].strftime("%Y-%m-%d")
                            created_at_for_sort = wanted_dict["created_at"]
                        elif hasattr(wanted_dict["created_at"], "timestamp"):
                            # Firestore Timestamp 物件
                            from datetime import datetime
                            dt = wanted_dict["created_at"].to_datetime()
                            created_at_str = dt.strftime("%Y-%m-%d")
                            created_at_for_sort = dt
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
@app.route("/message", methods=["GET", "POST"])
def message():
    if "user" not in session:
        return redirect("/login")  # 未登入則跳轉到登入頁
    return render_template("message.html")  # 渲染聊天室頁面

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
    return render_template("collects.html")  # 渲染個人收藏頁面

# 書籍詳情
@app.route("/book/<book_id>", methods=["GET"])
def book_detail(book_id):
    if "user" not in session:
        return redirect("/login")
    
    try:
        # 獲取書籍資料
        book_ref = db.collection("books").document(book_id)
        book_doc = book_ref.get()
        
        if not book_doc.exists:
            return redirect("/?error=book_not_found")
        
        book_dict = book_doc.to_dict()
        book_dict["id"] = book_doc.id
        
        # 處理圖片
        if not book_dict.get("front_image"):
            book_dict["front_image"] = "static/images/book_original.png"
        
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
        evaluations_ref = db.collection("evaluations")
        try:
            # 根據書名查找所有相關評價
            evaluations_query = evaluations_ref.where("book_title", "==", book_dict.get("title", "")).order_by("created_at", direction=firestore.Query.DESCENDING).limit(50)
            evaluations = evaluations_query.stream()
        except:
            # 如果排序失敗，使用簡單查詢
            evaluations_query = evaluations_ref.where("book_title", "==", book_dict.get("title", "")).limit(50)
            evaluations = evaluations_query.stream()
        
        reviews = []
        ratings = []
        for evaluation in evaluations:
            eval_dict = evaluation.to_dict()
            eval_dict["id"] = evaluation.id
            
            # 收集評分用於計算平均評分
            rating = eval_dict.get("rating", 0)
            if rating > 0:
                ratings.append(rating)
            
            # 處理時間戳記
            if "created_at" in eval_dict and eval_dict["created_at"]:
                try:
                    if hasattr(eval_dict["created_at"], "strftime"):
                        eval_dict["created_at"] = eval_dict["created_at"].strftime("%Y-%m-%d")
                    else:
                        eval_dict["created_at"] = str(eval_dict["created_at"])[:10]
                except:
                    eval_dict["created_at"] = str(eval_dict["created_at"])[:10] if eval_dict["created_at"] else ""
            
            reviews.append(eval_dict)
        
        # 計算平均評分
        if ratings:
            avg_rating = sum(ratings) / len(ratings)
            book_dict["rating"] = avg_rating
        else:
            book_dict["rating"] = 0
        
        return render_template("book_detail.html", book=book_dict, reviews=reviews)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"錯誤：{e}")
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
        
        return render_template("google_book_detail.html", 
                             book_details=book_details,
                             providers=providers,
                             google_id=google_id,
                             search_query=search_query)
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

# 我想要書
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
            favorites_query = favorites_ref.where("book_id", "==", book_id)
            favorites = favorites_query.stream()
            
            deleted_favorites_count = 0
            for favorite in favorites:
                try:
                    favorite.reference.delete()
                    deleted_favorites_count += 1
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
            
            department = request.form.get("department", "")
            major = request.form.get("major", "")
            grade = request.form.get("grade", "")
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
            if not department:
                return render_template("add_book.html", error="請選擇系所。")
            if not major:
                return render_template("add_book.html", error="請選擇科系。")
            if not grade:
                return render_template("add_book.html", error="請選擇年級。")
            if not course_name:
                return render_template("add_book.html", error="請輸入課程名稱。")
            if not instructor:
                return render_template("add_book.html", error="請輸入授課老師。")
            if not review_content:
                return render_template("add_book.html", error="請輸入詳細內容。")
            
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
                "department": department,
                "major": major,
                "grade": grade,
                "course_name": course_name,
                "instructor": instructor,
                "review_content": review_content,
                "reviewer_email": session["user"],
                "created_at": firestore.SERVER_TIMESTAMP
            }
            
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
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
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

if __name__ == "__main__":
    # 允許從其他設備訪問（手機測試）
    # host='0.0.0.0' 表示監聽所有網路介面
    # 在手機瀏覽器中訪問: http://你的電腦IP:5000
    app.run(host='0.0.0.0', port=5000, debug=True)