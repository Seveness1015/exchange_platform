"""
AI 推薦模塊
處理 OpenAI API 調用和推薦生成
"""
import os

# 嘗試導入 OpenAI（如果未安裝則使用規則生成）
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("警告：未安裝 openai 套件，將使用規則生成推薦。請執行 'pip install openai' 安裝。")

# 全局 OpenAI 客戶端
openai_client = None

def init_openai():
    """初始化 OpenAI 客戶端"""
    global openai_client
    
    from app.config import Config
    openai_api_key = Config.get_openai_api_key()
    
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
    
    return openai_client

def get_openai_client():
    """獲取 OpenAI 客戶端實例"""
    global openai_client
    if openai_client is None:
        init_openai()
    return openai_client

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
    client = get_openai_client()
    
    # 如果沒有設置 API Key，返回 None（將使用規則生成）
    if not client:
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
        response = client.chat.completions.create(
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

