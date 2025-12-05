"""
個人資料相關路由
處理個人資料、設置、密碼修改等功能
"""
from flask import Blueprint, render_template, request, redirect, session, url_for, jsonify, current_app
from app.utils.firebase import get_db, get_auth
from app.utils.helpers import convert_to_utc8, get_friendly_error_message
from app.config import Config
import firebase_admin.firestore as firestore
import requests
from datetime import datetime

profile_bp = Blueprint('profile', __name__)

@profile_bp.route("/profile", methods=["GET", "POST"])
def profile():
    if "user" not in session:
        return redirect(url_for("auth.login"))  # 未登入則跳轉到登入頁
    
    try:
        db = get_db()
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
            
            # 查詢所有該用戶的「我想要書」
            wanted_books_query = wanted_books_ref.where("requester_email", "==", view_user).limit(100)
            wanted_books = wanted_books_query.stream()
            
            total_count = 0
            for wanted_book in wanted_books:
                total_count += 1
                wanted_dict = wanted_book.to_dict()
                wanted_dict["id"] = wanted_book.id
                
                # 調試輸出：顯示每條記錄的資訊
                print(f"找到「我想要書」記錄：ID={wanted_book.id}, requester_email={wanted_dict.get('requester_email')}, status={wanted_dict.get('status', 'None')}, book_title={wanted_dict.get('book_title', 'None')}")
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

@profile_bp.route("/setting", methods=["GET", "POST"])
def setting():
    if "user" not in session:
        return redirect(url_for("auth.login"))  # 未登入則跳轉到登入頁
    return render_template("setting.html")  # 渲染設定頁面

@profile_bp.route("/edit_profile", methods=["GET", "POST"])
def edit_profile():
    if "user" not in session:
        return redirect(url_for("auth.login"))
    
    db = get_db()
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
            
            return redirect(url_for("profile.profile", success="profile_updated"))
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

@profile_bp.route("/change_password", methods=["GET", "POST"])
def change_password():
    if "user" not in session:
        return redirect(url_for("auth.login"))
    
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
            auth_firebase = get_auth()
            firebase_api_key = Config.get_firebase_api_key()
            
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
                    return redirect(url_for("profile.change_password", success="password_changed"))
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

@profile_bp.route("/delete_account", methods=["POST"])
def delete_account():
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        db = get_db()
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
        print(f"用戶 {current_user} 請求刪除帳號")
        
        # 清除 session
        session.pop("user", None)
        
        return jsonify({"success": True, "message": "帳號已刪除"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500
