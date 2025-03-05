import firebase_admin
import pyrebase
from firebase_admin import credentials, firestore, auth
from flask_frozen import Freezer
from flask import Flask, render_template, request, redirect, session
from dotenv import load_dotenv
import os

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
    if "user" in session:
        return render_template("/index.html")  # 已登入->主頁面
    else:
        return redirect("/login")  # 未登入->登入頁面


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        password_check = request.form["password-check"]
        if password_check != password:
            return render_template("register.html",erro_wrongPassword = True)
        try:
            user = auth_firebase.create_user_with_email_and_password(email, password)
            session["user"] = email
            return redirect("/")
        except:
            return render_template("register.html", error=True)
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        try:
            user = auth_firebase.sign_in_with_email_and_password(email, password)
            session["user"] = email
            return redirect("/")
        except:
            return render_template("login.html", error=True)
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")  



if __name__ == "__main__":
    app.run
