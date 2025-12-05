"""
訊息相關路由
處理聊天室功能
"""
from flask import Blueprint, render_template, request, redirect, session, url_for
from app.utils.firebase import get_db
from app.utils.helpers import convert_to_utc8, get_message_sort_key
import firebase_admin.firestore as firestore
from datetime import datetime

message_bp = Blueprint('message', __name__)

@message_bp.route("/message", methods=["GET"])
def message():
    if "user" not in session:
        return redirect(url_for("auth.login"))
    
    db = get_db()
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
            return redirect(url_for("message.message"))
    
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
            return redirect(url_for("books.home"))
    
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
