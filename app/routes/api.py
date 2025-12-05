"""
API 相關路由
處理各種 API 端點
"""
from flask import Blueprint, request, session, jsonify
from app.utils.firebase import get_db
from app.utils.helpers import convert_to_utc8, get_message_sort_key
import firebase_admin.firestore as firestore
from firebase_admin import storage
from datetime import datetime, timezone, timedelta
import time

api_bp = Blueprint('api', __name__)

@api_bp.route("/api/chat/<chat_id>/send", methods=["POST"])
def send_message(chat_id):
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        db = get_db()
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

@api_bp.route("/api/chat/<chat_id>/messages", methods=["GET"])
def get_messages(chat_id):
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        db = get_db()
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

@api_bp.route("/api/my-books", methods=["GET"])
def get_my_books():
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        db = get_db()
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

@api_bp.route("/api/chat/<chat_id>/transaction_reminder", methods=["GET"])
def get_transaction_reminder(chat_id):
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        db = get_db()
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

@api_bp.route("/api/chat/<chat_id>/transaction_reminder", methods=["POST"])
def create_or_update_transaction_reminder(chat_id):
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        db = get_db()
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

@api_bp.route("/api/unread-messages/count", methods=["GET"])
def get_unread_messages_count():
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        db = get_db()
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

@api_bp.route("/api/chat/<chat_id>/transaction_reminder/complete", methods=["POST"])
def complete_transaction(chat_id):
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        db = get_db()
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
        
        # 驗證當前用戶是否是賣家（根據 created_by）
        if reminder_dict.get("created_by") != current_user:
            return jsonify({"success": False, "error": "只有提供書籍的人可以完成交易"}), 403
        
        # 標記交易提醒為已完成
        transaction_id = reminder.id
        reminder.reference.update({
            "completed": True,
            "completed_at": firestore.SERVER_TIMESTAMP,
            "completed_by": current_user
        })
        
        # 刪除書籍（從資料庫中刪除）
        book_ref = db.collection("books").document(book_id)
        book_doc = book_ref.get()
        if not book_doc.exists:
            return jsonify({"success": False, "error": "書籍不存在"}), 404
        
        book_dict = book_doc.to_dict()
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

@api_bp.route("/api/transaction/<transaction_id>/evaluation/status", methods=["GET"])
def get_transaction_evaluation_status(transaction_id):
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        db = get_db()
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

@api_bp.route("/api/transaction/<transaction_id>/evaluation", methods=["POST"])
def submit_transaction_evaluation(transaction_id):
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"}), 401
    
    try:
        db = get_db()
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
