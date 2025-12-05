"""
認證相關路由
處理註冊、登入、登出、忘記密碼等功能
"""
from flask import Blueprint, render_template, request, redirect, session
import requests
from app.utils.firebase import get_auth, get_db
from app.config import Config
from app.utils.helpers import get_friendly_error_message

auth_bp = Blueprint('auth', __name__)

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """註冊頁面"""
    # 獲取 reCAPTCHA Site Key（用於前端顯示）
    recaptcha_site_key = Config.get_recaptcha_site_key()
    recaptcha_secret_key = Config.get_recaptcha_secret_key()
    
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
        auth_firebase = get_auth()

        try:
            # 創建 Firebase 使用者
            user = auth_firebase.create_user_with_email_and_password(email, password)
            print(f"User created successfully: {user['localId']}")

            # 發送驗證郵件
            try:
                if 'idToken' not in user:
                    user = auth_firebase.sign_in_with_email_and_password(email, password)
                
                auth_firebase.send_email_verification(user['idToken'])
                print(f"Verification email sent successfully to {email}!")
            except Exception as email_error:
                print(f"Error sending verification email: {email_error}")
                return render_template("register.html", 
                                     email=True, 
                                     email_warning="帳號已創建，但驗證郵件發送可能失敗，請稍後在登入頁面重新發送驗證郵件。",
                                     recaptcha_site_key=recaptcha_site_key)

            return render_template("register.html", email=True, recaptcha_site_key=recaptcha_site_key)
        except Exception as e:
            error_msg = str(e)
            print(f"Registration Error: {error_msg}")
            
            friendly_error = get_friendly_error_message(error_msg)
            return render_template("register.html", error=friendly_error, recaptcha_site_key=recaptcha_site_key)

    return render_template("register.html", recaptcha_site_key=recaptcha_site_key)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """登入頁面"""
    if "user" in session:
        return redirect("/")  # 已登入則跳轉到首頁
    
    if request.method == "POST":
        std_num = request.form.get("std_num", "").strip()
        password = request.form.get("password", "")
        
        if not std_num or not password:
            return render_template("login.html", error=True)
        
        email = std_num + "@mail.ntust.edu.tw"
        auth_firebase = get_auth()

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
            return render_template("login.html", error=True)

    return render_template("login.html")


@auth_bp.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    """忘記密碼頁面"""
    if "user" in session:
        return redirect("/")  # 已登入則跳轉到首頁
    
    if request.method == "POST":
        std_num = request.form.get("std_num", "").strip()
        
        if not std_num:
            return render_template("forgot_password.html", error="請輸入學號。")
        
        email = std_num + "@mail.ntust.edu.tw"
        auth_firebase = get_auth()
        
        try:
            # 使用 Firebase Auth 發送密碼重設郵件
            auth_firebase.send_password_reset_email(email)
            return render_template("forgot_password.html", success=True)
        except Exception as e:
            error_msg = str(e)
            friendly_error = get_friendly_error_message(error_msg)
            return render_template("forgot_password.html", error=friendly_error)
    
    return render_template("forgot_password.html")


@auth_bp.route("/logout")
def logout():
    """登出"""
    session.pop("user", None)
    return redirect("/login")

