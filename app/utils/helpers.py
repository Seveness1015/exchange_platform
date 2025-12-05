"""
輔助函數模塊
包含通用的工具函數
"""
from datetime import datetime, timezone, timedelta
import re
from PIL import Image
import io
import uuid
from firebase_admin import storage


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


def normalize_text_for_matching(text):
    """標準化文本用於匹配（移除空格、轉小寫、移除特殊字符）"""
    if not text:
        return ""
    # 轉小寫
    text = text.lower()
    # 移除所有空格
    text = re.sub(r'\s+', '', text)
    # 移除常見的標點符號
    text = re.sub(r'[，。、；：！？「」『』（）【】《》〈〉]', '', text)
    return text


def calculate_similarity_for_matching(str1, str2):
    """計算兩個字符串的相似度（0-1）"""
    if not str1 or not str2:
        return 0.0
    
    # 標準化
    norm1 = normalize_text_for_matching(str1)
    norm2 = normalize_text_for_matching(str2)
    
    if not norm1 or not norm2:
        return 0.0
    
    # 如果完全相同
    if norm1 == norm2:
        return 1.0
    
    # 計算最長公共子序列長度
    def lcs_length(s1, s2):
        m, n = len(s1), len(s2)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if s1[i-1] == s2[j-1]:
                    dp[i][j] = dp[i-1][j-1] + 1
                else:
                    dp[i][j] = max(dp[i-1][j], dp[i][j-1])
        return dp[m][n]
    
    lcs = lcs_length(norm1, norm2)
    max_len = max(len(norm1), len(norm2))
    
    if max_len == 0:
        return 0.0
    
    return lcs / max_len


def match_isbn_for_matching(isbn1, isbn2):
    """匹配兩個 ISBN（處理不同格式）"""
    if not isbn1 or not isbn2:
        return False
    
    # 移除所有非數字字符
    isbn1_clean = re.sub(r'[^0-9X]', '', str(isbn1).upper())
    isbn2_clean = re.sub(r'[^0-9X]', '', str(isbn2).upper())
    
    # 如果完全相同
    if isbn1_clean == isbn2_clean:
        return True
    
    # 如果一個是 10 位，一個是 13 位，嘗試轉換
    if len(isbn1_clean) == 10 and len(isbn2_clean) == 13:
        # 簡單檢查：13 位 ISBN 的前綴通常是 978 或 979
        if isbn2_clean.startswith('978') or isbn2_clean.startswith('979'):
            # 比較後 10 位（去掉前綴和校驗碼）
            if isbn1_clean[:-1] == isbn2_clean[3:-1]:
                return True
    elif len(isbn1_clean) == 13 and len(isbn2_clean) == 10:
        if isbn1_clean.startswith('978') or isbn1_clean.startswith('979'):
            if isbn1_clean[3:-1] == isbn2_clean[:-1]:
                return True
    
    return False


def is_same_book(google_title, google_authors, google_isbn_list, book_title, book_author, book_isbn):
    """判斷 Google Books 的書籍是否與平台上的書籍相同"""
    # 1. ISBN 匹配（最準確）
    if book_isbn and google_isbn_list:
        for google_isbn in google_isbn_list:
            if match_isbn_for_matching(book_isbn, google_isbn):
                return True
    
    # 2. 書名和作者匹配
    title_similarity = calculate_similarity_for_matching(google_title, book_title)
    author_similarity = 0.0
    
    if google_authors and book_author:
        # 比較所有作者
        google_authors_list = [a.strip() for a in google_authors.split(',')]
        book_authors_list = [a.strip() for a in book_author.split(',')]
        
        for g_author in google_authors_list:
            for b_author in book_authors_list:
                sim = calculate_similarity_for_matching(g_author, b_author)
                author_similarity = max(author_similarity, sim)
    
    # 如果書名相似度 > 0.8 且作者相似度 > 0.7，認為是同一本書
    if title_similarity > 0.8 and author_similarity > 0.7:
        return True
    
    # 如果書名相似度 > 0.9，即使作者不匹配也認為可能是同一本書（可能是作者信息不完整）
    if title_similarity > 0.9:
        return True
    
    return False


def compress_image(image_file, max_size=(1200, 1600), quality=85):
    """壓縮圖片"""
    try:
        # 打開圖片
        img = Image.open(image_file)
        
        # 轉換為 RGB（如果是 RGBA）
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # 調整大小（保持長寬比）
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # 保存到內存
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=quality, optimize=True)
        output.seek(0)
        
        return output
    except Exception as e:
        print(f"壓縮圖片時發生錯誤：{e}")
        # 如果壓縮失敗，返回原始文件
        image_file.seek(0)
        return image_file


def upload_image_to_firebase_storage(image_file, user_email, image_type="front"):
    """上傳圖片到 Firebase Storage"""
    try:
        # 壓縮圖片
        compressed_image = compress_image(image_file)
        
        # 生成唯一文件名
        file_extension = "jpg"
        filename = f"{user_email}/{image_type}_{uuid.uuid4()}.{file_extension}"
        
        # 上傳到 Firebase Storage
        bucket = storage.bucket()
        blob = bucket.blob(filename)
        blob.upload_from_file(compressed_image, content_type='image/jpeg')
        
        # 設置公開讀取權限
        blob.make_public()
        
        # 獲取公開 URL
        image_url = blob.public_url
        
        return image_url
    except Exception as e:
        print(f"上傳圖片時發生錯誤：{e}")
        raise


def get_friendly_error_message(error_msg):
    """將 Firebase 錯誤訊息轉換為友善的中文訊息"""
    error_msg_lower = error_msg.lower()
    
    if "email already exists" in error_msg_lower or "email-already-in-use" in error_msg_lower:
        return "此電子郵件已被註冊，請使用其他電子郵件或嘗試登入。"
    elif "invalid email" in error_msg_lower or "invalid-email" in error_msg_lower:
        return "電子郵件格式不正確，請檢查後再試。"
    elif "weak password" in error_msg_lower or "password-too-short" in error_msg_lower:
        return "密碼太短，請使用至少 6 個字符的密碼。"
    elif "wrong password" in error_msg_lower or "wrong-password" in error_msg_lower or "invalid-credential" in error_msg_lower:
        return "電子郵件或密碼錯誤，請檢查後再試。"
    elif "user not found" in error_msg_lower or "user-not-found" in error_msg_lower:
        return "找不到此用戶，請確認電子郵件是否正確。"
    elif "network" in error_msg_lower or "network-request-failed" in error_msg_lower:
        return "網絡連接失敗，請檢查網絡連接後再試。"
    elif "too many requests" in error_msg_lower or "too-many-requests" in error_msg_lower:
        return "請求過於頻繁，請稍後再試。"
    else:
        return f"發生錯誤：{error_msg}"

