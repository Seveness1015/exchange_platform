import firebase_admin
import pyrebase
from firebase_admin import credentials, firestore
from flask import Flask, render_template, request, redirect, session,jsonify
from dotenv import load_dotenv
import os
import datetime
import requests

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
    
    try:
        # 從 Firestore 讀取其他人的書籍（排除當前用戶）
        current_user = session["user"]
        books_ref = db.collection("books")
        
        # 查詢所有狀態為 available 的書籍
        # 注意：Firestore 不支援 != 運算符，所以我們先查詢所有，然後在 Python 中過濾
        # 如果 order_by 需要索引，可以先移除排序
        try:
            books_query = books_ref.where("status", "==", "available").order_by("created_at", direction=firestore.Query.DESCENDING).limit(50)
            books = books_query.stream()
        except Exception as order_error:
            # 如果排序失敗（可能是因為缺少索引），則不使用排序
            print(f"排序查詢失敗，使用簡單查詢: {order_error}")
            books_query = books_ref.where("status", "==", "available").limit(50)
            books = books_query.stream()
        
        books_list = []
        for book in books:
            book_dict = book.to_dict()
            book_dict["id"] = book.id
            
            # 過濾掉當前用戶的書籍
            seller_email = book_dict.get("seller_email", "")
            if seller_email == current_user:
                continue
            
            # 處理時間戳記
            if "created_at" in book_dict and book_dict["created_at"]:
                try:
                    # 如果是 Timestamp 物件，轉換為字串
                    if hasattr(book_dict["created_at"], "strftime"):
                        book_dict["created_at"] = book_dict["created_at"].strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        book_dict["created_at"] = str(book_dict["created_at"])
                except:
                    book_dict["created_at"] = str(book_dict["created_at"])
            
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
            
            # 處理賣家電子郵件顯示（只顯示學號部分）
            seller_email = book_dict.get("seller_email", "")
            if seller_email:
                # 從 email 中提取學號（例如：B12345678@mail.ntust.edu.tw -> B12345678）
                if "@" in seller_email:
                    book_dict["seller_display"] = seller_email.split("@")[0]
                else:
                    book_dict["seller_display"] = seller_email
            else:
                book_dict["seller_display"] = "未知"
            
            # 如果沒有封面圖片，使用預設圖片路徑
            if not book_dict.get("front_image"):
                book_dict["front_image"] = "static/images/user_cat01.png"
            
            books_list.append(book_dict)
        
        # 如果沒有使用排序，在 Python 中排序（按建立時間降序）
        if len(books_list) > 0 and "created_at" in books_list[0]:
            try:
                books_list.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            except:
                pass
        
        # 限制顯示數量
        books_list = books_list[:20]
        
        return render_template("index.html", books=books_list)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"錯誤：{e}")
        # 如果發生錯誤，仍然顯示頁面，只是沒有書籍
        return render_template("index.html", books=[])


# 註冊
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["std_num"] + "@mail.ntust.edu.tw"
        password = request.form["password"]
        password_check = request.form["password-check"]

        try:
            # 創建 Firebase 使用者
            user = auth_firebase.create_user_with_email_and_password(email, password)
            print(f"User created: {user['localId']}")

            # 讓 Firebase 直接發送驗證信
            auth_firebase.send_email_verification(user['idToken'])
            print("Verification email sent!")

            return render_template("register.html", email=True)
        except Exception as e:
            print(f"Error: {e}")
            return render_template("register.html", error=True)

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

            session["user"] = email
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
        
        # 從 email 中提取學號作為顯示名稱
        if "@" in view_user:
            user_display = view_user.split("@")[0]
        else:
            user_display = view_user
        
        # 獲取用戶的書籍（提供的）
        books_ref = db.collection("books")
        provided_books = []
        
        try:
            # 使用簡單查詢（只查詢 seller_email），然後在 Python 中過濾和排序
            # 這樣可以避免需要 Firestore 索引
            try:
                books_query = books_ref.where("seller_email", "==", view_user).limit(100)
                books = books_query.stream()
                
                for book in books:
                    book_dict = book.to_dict()
                    book_dict["id"] = book.id
                    
                    # 過濾掉 status 不是 "available" 的記錄
                    status = book_dict.get("status", "available")
                    if status != "available":
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
                        book_dict["front_image"] = "static/images/user_cat01.png"
                    
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
    
    if request.method == "POST":
        try:
            # 獲取表單資料
            display_name = request.form.get("display_name", "").strip()
            # TODO: 處理頭像上傳
            
            # 更新用戶資料到 Firestore（如果需要的話）
            # 目前先簡單處理
            return redirect("/profile")
        except Exception as e:
            import traceback
            traceback.print_exc()
            return render_template("edit_profile.html", error=str(e))
    
    # 獲取當前用戶資訊
    current_user = session["user"]
    if "@" in current_user:
        user_display = current_user.split("@")[0]
    else:
        user_display = current_user
    
    return render_template("edit_profile.html", user_display=user_display, user_email=current_user)

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
            book_dict["front_image"] = "static/images/user_cat01.png"
        
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

# 搜尋功能
@app.route("/search", methods=["GET"])
def search():
    if "user" not in session:
        return redirect("/login")
    
    try:
        search_type = request.args.get("type", "books")  # books 或 wanted
        search_query = request.args.get("q", "").strip()
        
        if not search_query:
            return redirect("/")
        
        current_user = session["user"]
        books_list = []
        wanted_books_list = []
        
        if search_type == "books":
            # 搜尋書籍
            books_ref = db.collection("books")
            try:
                # 查詢所有狀態為 available 的書籍
                books_query = books_ref.where("status", "==", "available").limit(100)
                books = books_query.stream()
            except:
                books_query = books_ref.where("status", "==", "available").limit(100)
                books = books_query.stream()
            
            for book in books:
                book_dict = book.to_dict()
                book_dict["id"] = book.id
                
                # 過濾掉當前用戶的書籍
                seller_email = book_dict.get("seller_email", "")
                if seller_email == current_user:
                    continue
                
                # 根據搜尋關鍵字過濾（書名、作者、ISBN）
                title = book_dict.get("title", "").lower()
                author = book_dict.get("author", "").lower()
                isbn = book_dict.get("isbn", "").lower()
                search_lower = search_query.lower()
                
                if search_lower in title or search_lower in author or search_lower in isbn:
                    # 處理時間戳記
                    if "created_at" in book_dict and book_dict["created_at"]:
                        try:
                            if hasattr(book_dict["created_at"], "strftime"):
                                book_dict["created_at"] = book_dict["created_at"].strftime("%Y-%m-%d %H:%M:%S")
                            else:
                                book_dict["created_at"] = str(book_dict["created_at"])
                        except:
                            book_dict["created_at"] = str(book_dict["created_at"])
                    
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
                    if seller_email:
                        if "@" in seller_email:
                            book_dict["seller_display"] = seller_email.split("@")[0]
                        else:
                            book_dict["seller_display"] = seller_email
                    else:
                        book_dict["seller_display"] = "未知"
                    
                    # 處理圖片
                    if not book_dict.get("front_image"):
                        book_dict["front_image"] = "static/images/user_cat01.png"
                    
                    books_list.append(book_dict)
        
        elif search_type == "wanted":
            # 搜尋「我想要書」的需求
            wanted_books_ref = db.collection("wanted_books")
            try:
                # 不再使用 status 過濾，直接查詢所有記錄
                wanted_books_query = wanted_books_ref.limit(100)
                wanted_books = wanted_books_query.stream()
            except Exception as query_error:
                print(f"查詢「我想要書」時發生錯誤：{query_error}")
                wanted_books = []
            
            for wanted_book in wanted_books:
                wanted_dict = wanted_book.to_dict()
                wanted_dict["id"] = wanted_book.id
                
                # 過濾掉已刪除的記錄（向後兼容舊資料）
                status = wanted_dict.get("status")
                if status == "deleted":
                    continue
                
                # 根據搜尋關鍵字過濾（書名、作者、ISBN）
                title = wanted_dict.get("book_title", "").lower()
                author = wanted_dict.get("author", "").lower()
                isbn = wanted_dict.get("isbn", "").lower()
                search_lower = search_query.lower()
                
                if search_lower in title or search_lower in author or search_lower in isbn:
                    # 處理時間戳記
                    if "created_at" in wanted_dict and wanted_dict["created_at"]:
                        try:
                            if hasattr(wanted_dict["created_at"], "strftime"):
                                wanted_dict["created_at"] = wanted_dict["created_at"].strftime("%Y-%m-%d")
                            else:
                                wanted_dict["created_at"] = str(wanted_dict["created_at"])[:10]
                        except:
                            wanted_dict["created_at"] = str(wanted_dict["created_at"])[:10] if wanted_dict["created_at"] else ""
                    
                    # 處理需求者電子郵件顯示
                    requester_email = wanted_dict.get("requester_email", "")
                    if requester_email:
                        if "@" in requester_email:
                            wanted_dict["requester_display"] = requester_email.split("@")[0]
                        else:
                            wanted_dict["requester_display"] = requester_email
                    else:
                        wanted_dict["requester_display"] = "未知"
                    
                    wanted_books_list.append(wanted_dict)
        
        return render_template("search_results.html", 
                             search_type=search_type,
                             search_query=search_query,
                             books=books_list,
                             wanted_books=wanted_books_list)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"錯誤：{e}")
        return render_template("search_results.html", 
                             search_type=search_type if 'search_type' in locals() else "books",
                             search_query=search_query if 'search_query' in locals() else "",
                             books=[],
                             wanted_books=[])

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
            
            department = request.form.get("department", "")
            major = request.form.get("major", "")
            grade = request.form.get("grade", "")
            course_name = request.form.get("course_name", "").strip()
            instructor = request.form.get("instructor", "").strip()
            review_content = request.form.get("review_content", "").strip()
            
            # 資料驗證
            if not book_title:
                return render_template("write_review.html", error="請輸入書名。")
            if not department:
                return render_template("write_review.html", error="請選擇系所。")
            if not major:
                return render_template("write_review.html", error="請選擇科系。")
            if not grade:
                return render_template("write_review.html", error="請選擇年級。")
            if not course_name:
                return render_template("write_review.html", error="請輸入課程名稱。")
            if not instructor:
                return render_template("write_review.html", error="請輸入授課老師。")
            if not review_content:
                return render_template("write_review.html", error="請輸入詳細內容。")
            
            # 儲存到 Firestore - evaluations collection
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
                
                # 處理圖片上傳（如果有的話）
                front_image = request.files.get("front_image")
                back_image = request.files.get("back_image")
                
                # TODO: 實作圖片上傳到 Firebase Storage
                # 目前先跳過圖片更新
                
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
        
        # 刪除書籍
        book_ref.delete()
        
        return jsonify({"success": True, "message": "書籍已刪除"})
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
                
                department = request.form.get("department", "")
                major = request.form.get("major", "")
                grade = request.form.get("grade", "")
                course_name = request.form.get("course_name", "").strip()
                instructor = request.form.get("instructor", "").strip()
                review_content = request.form.get("review_content", "").strip()
                
                # 資料驗證
                if not book_title:
                    return render_template("edit_review.html", review=review_dict, error="請輸入書名。")
                if not department:
                    return render_template("edit_review.html", review=review_dict, error="請選擇系所。")
                if not major:
                    return render_template("edit_review.html", review=review_dict, error="請選擇科系。")
                if not grade:
                    return render_template("edit_review.html", review=review_dict, error="請選擇年級。")
                if not course_name:
                    return render_template("edit_review.html", review=review_dict, error="請輸入課程名稱。")
                if not instructor:
                    return render_template("edit_review.html", review=review_dict, error="請輸入授課老師。")
                if not review_content:
                    return render_template("edit_review.html", review=review_dict, error="請輸入詳細內容。")
                
                # 更新書評資料
                update_data = {
                    "book_title": book_title,
                    "rating": rating,
                    "department": department,
                    "major": major,
                    "grade": grade,
                    "course_name": course_name,
                    "instructor": instructor,
                    "review_content": review_content,
                }
                
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
        
        # 刪除書評
        review_ref.delete()
        
        return jsonify({"success": True, "message": "書評已刪除"})
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
            
            # 處理圖片上傳（目前先存儲路徑，實際圖片上傳功能需要 Firebase Storage）
            front_image = request.files.get("front_image")
            back_image = request.files.get("back_image")
            
            front_image_url = ""
            back_image_url = ""
            
            # TODO: 實作圖片上傳到 Firebase Storage
            # 目前先跳過圖片上傳，專注於資料結構
            
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
                "seller_email": session["user"],
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

# 測試路由 - 查詢所有書籍（僅供測試用）
@app.route("/test/books")
def test_books():
    if "user" not in session:
        return redirect("/login")
    
    try:
        books_ref = db.collection("books")
        books = books_ref.limit(10).stream()  # 限制查詢 10 筆
        
        books_list = []
        for book in books:
            book_dict = book.to_dict()
            book_dict["id"] = book.id
            # 處理時間戳記
            if "created_at" in book_dict and book_dict["created_at"]:
                book_dict["created_at"] = str(book_dict["created_at"])
            books_list.append(book_dict)
        
        return jsonify({
            "success": True,
            "count": len(books_list),
            "books": books_list
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# 測試路由 - 查詢所有評價（僅供測試用）
@app.route("/test/evaluations")
def test_evaluations():
    if "user" not in session:
        return redirect("/login")
    
    try:
        evaluations_ref = db.collection("evaluations")
        evaluations = evaluations_ref.limit(10).stream()  # 限制查詢 10 筆
        
        evaluations_list = []
        for evaluation in evaluations:
            eval_dict = evaluation.to_dict()
            eval_dict["id"] = evaluation.id
            # 處理時間戳記
            if "created_at" in eval_dict and eval_dict["created_at"]:
                eval_dict["created_at"] = str(eval_dict["created_at"])
            evaluations_list.append(eval_dict)
        
        return jsonify({
            "success": True,
            "count": len(evaluations_list),
            "evaluations": evaluations_list
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# 傳送訊息
# @app.route("/send_message", methods=["POST"])
# def send_message():
#     data = request.json
#     chat_id = data["chat_id"]
#     sender = data["sender"]
#     text = data.get("text", "")

#     if not chat_id or not sender:
#         return jsonify({"error": "缺少 chat_id 或 sender"}), 400

#     message_ref = db.collection("chats").document(chat_id).collection("messages").document()
#     message_ref.set({
#         "sender": sender,
#         "text": text,
#         "timestamp": datetime.datetime.utcnow()
#     })

#     return jsonify({"message": "訊息已送出"}), 200

if __name__ == "__main__":
    app.run(debug=True)