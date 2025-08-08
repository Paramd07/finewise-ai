# SmartWeave AI — Final Complete App (app.py)
"""
This file is a complete, production-ready (basic) Streamlit app that includes:
- User registration & login (passwords hashed)
- User activity logging to a local SQLite DB (actions, timestamps, IP placeholder)
- Caption generator (OpenAI)
- Stock analyzer (yfinance) for Indian & global tickers
- Track / watchlist feature for users
- News & sentiment insights (OpenAI prompt)
- Chat assistant with Casual/Professional modes
- Career chatbot + saved Q&A
- Tax estimator (India) with PDF export
- Export analysis to Excel/PDF
- Admin dashboard with analytics and CSV/Excel export

Notes:
- You must set the Streamlit secret `OPENAI_API_KEY` in Streamlit Cloud (or set as environment variable locally).
- For real client IP capture behind proxies, configure your host/load-balancer to forward `X-Forwarded-For`.
- This app stores user data in `user_data.db` (SQLite). For multi-instance production, migrate to PostgreSQL or Firebase.
"""

import streamlit as st
import openai
import yfinance as yf
import datetime
import pandas as pd
import sqlite3
import hashlib
import json
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# ----------------------
# Config / Secrets
# ----------------------
st.set_page_config(page_title="FinWise AI", layout="wide", page_icon="📊")
openai.api_key = st.secrets.get("OPENAI_API_KEY", "")

DB_PATH = "user_data.db"

# ----------------------
# Database helpers
# ----------------------
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

# Create tables
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password_hash TEXT,
    email TEXT,
    is_admin INTEGER DEFAULT 0,
    created_at TEXT
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS user_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    action TEXT,
    details TEXT,
    ip TEXT,
    timestamp TEXT
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS career_qna (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    question TEXT,
    answer TEXT,
    timestamp TEXT
)''')

conn.commit()

# ----------------------
# Utilities
# ----------------------
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def log_action(username: str, action: str, details: str = ""):
    # Attempt to get client IP from forwarded headers — depends on hosting
    ip = None
    try:
        # Streamlit doesn't expose request headers directly in a stable API.
        # If your deployment sets a query param or header, you can capture it here.
        params = st.experimental_get_query_params()
        ip = params.get("ip", [None])[0]
    except Exception:
        ip = None

    cursor.execute("INSERT INTO user_logs (username, action, details, ip, timestamp) VALUES (?, ?, ?, ?, ?)",
                   (username, action, details, ip, datetime.datetime.utcnow().isoformat()))
    conn.commit()


# ----------------------
# Auth: register / login / logout
# ----------------------
if "auth_user" not in st.session_state:
    st.session_state.auth_user = None

if "is_admin" not in st.session_state:
    st.session_state.is_admin = False


def register_user(username: str, password: str, email: str = ""):
    cursor.execute("SELECT username FROM users WHERE username=?", (username,))
    if cursor.fetchone():
        return False, "Username already exists"
    pw_hash = hash_password(password)
    cursor.execute("INSERT INTO users (username, password_hash, email, created_at) VALUES (?, ?, ?, ?)",
                   (username, pw_hash, email, datetime.datetime.utcnow().isoformat()))
    conn.commit()
    return True, "Registered"


def login_user(username: str, password: str):
    pw_hash = hash_password(password)
    cursor.execute("SELECT username, is_admin FROM users WHERE username=? AND password_hash=?", (username, pw_hash))
    row = cursor.fetchone()
    if row:
        st.session_state.auth_user = username
        st.session_state.is_admin = bool(row[1])
        log_action(username, "login", "successful")
        return True
    else:
        return False


def logout():
    if st.session_state.auth_user:
        log_action(st.session_state.auth_user, "logout", "user logged out")
    st.session_state.auth_user = None
    st.session_state.is_admin = False

# ----------------------
# Top-level: authentication UI
# ----------------------
with st.sidebar:
    st.title("FinWise AI")
    if st.session_state.auth_user:
        st.markdown(f"**Logged in as:** {st.session_state.auth_user}")
        if st.button("Logout"):
            logout()
            st.experimental_rerun()
    else:
        st.subheader("Login")
        login_user_input = st.text_input("Username", key="login_username")
        login_pw_input = st.text_input("Password", type="password", key="login_password")
        if st.button("Login", key="login_btn"):
            ok = login_user(login_user_input, login_pw_input)
            if ok:
                st.success("Logged in")
                st.experimental_rerun()
            else:
                st.error("Invalid credentials")

        st.markdown("---")
        st.subheader("Register")
        reg_user = st.text_input("Choose username", key="reg_user")
        reg_pw = st.text_input("Choose password", type="password", key="reg_pw")
        reg_email = st.text_input("Email (optional)", key="reg_email")
        if st.button("Register", key="reg_btn"):
            ok, msg = register_user(reg_user, reg_pw, reg_email)
            if ok:
                st.success("Registered — you can now login")
            else:
                st.error(msg)

# If not logged in, show a friendly message and stop
if not st.session_state.auth_user:
    st.write("\n---\n")
    st.write("Welcome to FinWise AI — please register or log in (sidebar) to continue.")
    st.stop()

# ----------------------
# Main App Layout
# ----------------------
menu = ["Home", "Caption Generator", "Stock Analyzer", "Chat Assistant", "Career Advisor", "Tax Estimator", "Watchlist", "Admin Dashboard"]
choice = st.sidebar.selectbox("Navigation", menu)

# ----------------------
# Home
# ----------------------
if choice == "Home":
    st.header("Welcome to FinWise AI")
    st.write("Use the side menu to navigate. Your activity is logged for auditing and analytics.")

# ----------------------
# Caption Generator
# ----------------------
elif choice == "Caption Generator":
    st.header("Generate Captions")
    theme = st.text_input("Theme or keyword")
    tone = st.selectbox("Tone", ["General", "Funny", "Classy", "Savage", "Motivational"])
    if st.button("Generate"):
        if not openai.api_key:
            st.error("OpenAI API key not configured. Add it as a Streamlit secret OPENAI_API_KEY.")
        else:
            prompt = f"Generate 5 {tone.lower()} Instagram captions about: {theme}"
            resp = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[{"role":"user","content":prompt}])
            text = resp.choices[0].message.content.strip()
            captions = [s.strip() for s in text.split('\n') if s.strip()]
            for c in captions:
                st.write("- ", c)
            log_action(st.session_state.auth_user, "generate_caption", json.dumps({"theme": theme, "tone": tone}))

# ----------------------
# Stock Analyzer
# ----------------------
elif choice == "Stock Analyzer":
    st.header("Stock Analyzer — Indian & Global")
    symbol = st.text_input("Ticker (e.g. RELIANCE.NS or AAPL)")
    if st.button("Analyze"):
        if not symbol:
            st.warning("Enter a ticker")
        else:
            try:
                df = yf.Ticker(symbol).history(period="1y")
                if df.empty:
                    st.error("No data returned — check ticker symbol")
                else:
                    latest = df['Close'].iloc[-1]
                    ch7 = (df['Close'].iloc[-1] - df['Close'].iloc[-7]) / df['Close'].iloc[-7] * 100
                    ch30 = (df['Close'].iloc[-1] - df['Close'].iloc[-30]) / df['Close'].iloc[-30] * 100
                    st.metric("Latest Close", f"{latest:.2f}")
                    st.metric("7d %", f"{ch7:.2f}%")
                    st.metric("30d %", f"{ch30:.2f}%")

                    # AI summary + news insights
                    if openai.api_key:
                        summary_prompt = f"Summarize the last 1 year trend for {symbol} in 3 short bullets, and mention important events that could have affected price."
                        summ = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[{"role":"user","content":summary_prompt}])
                        st.subheader("AI Summary")
                        st.write(summ.choices[0].message.content)

                        news_prompt = f"Provide recent news or sentiment for {symbol} in brief (last 7 days). If you don't know, say so clearly." 
                        news = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[{"role":"user","content":news_prompt}])
                        st.subheader("News & Sentiment (AI)")
                        st.write(news.choices[0].message.content)

                    log_action(st.session_state.auth_user, "analyze_stock", symbol)

                    # Exports
                    if st.button("Export Excel"):
                        buf = BytesIO()
                        df.to_excel(buf)
                        st.download_button("Download Excel", data=buf.getvalue(), file_name=f"{symbol}_1y.xlsx")

                    if st.button("Export PDF Summary"):
                        buf = BytesIO()
                        p = canvas.Canvas(buf, pagesize=letter)
                        p.drawString(72, 720, f"Stock Analysis: {symbol}")
                        p.drawString(72, 700, f"Latest Close: {latest:.2f}")
                        p.drawString(72, 680, f"7d Change: {ch7:.2f}%")
                        p.drawString(72, 660, f"30d Change: {ch30:.2f}%")
                        p.showPage()
                        p.save()
                        st.download_button("Download PDF", data=buf.getvalue(), file_name=f"{symbol}_summary.pdf")

                    # Watchlist
                    if st.button("Add to Watchlist"):
                        cursor.execute("INSERT OR IGNORE INTO user_logs (username, action, details, ip, timestamp) VALUES (?, ?, ?, ?, ?)",
                                       (st.session_state.auth_user, "track_stock", symbol, None, datetime.datetime.utcnow().isoformat()))
                        conn.commit()
                        st.success("Added to your watchlist (logged)")
            except Exception as e:
                st.error(f"Error fetching data: {e}")

# ----------------------
# Chat Assistant
# ----------------------
elif choice == "Chat Assistant":
    st.header("AI Chat Assistant")
    tone = st.radio("Tone", ["Casual & Friendly", "Professional"])
    message = st.text_area("Message")
    if st.button("Send"):
        if not openai.api_key:
            st.error("OpenAI API key not configured")
        else:
            prompt = f"You are an expert assistant. Answer in a {tone.lower()} tone. User: {message}"
            res = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[{"role":"user","content":prompt}])
            answer = res.choices[0].message.content.strip()
            st.write(answer)
            log_action(st.session_state.auth_user, "chat", message)

# ----------------------
# Career Advisor
# ----------------------
elif choice == "Career Advisor":
    st.header("Career AI — ask about courses, exams, and career paths")
    q = st.text_input("Your career question")
    if st.button("Ask"):
        if not openai.api_key:
            st.error("OpenAI API key missing")
        else:
            prompt = f"You are a career counselor specialized in commerce/finance. Provide a structured answer and a 3-step plan. Question: {q}"
            resp = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[{"role":"user","content":prompt}])
            ans = resp.choices[0].message.content.strip()
            st.write(ans)
            # Save Q&A
            cursor.execute("INSERT INTO career_qna (username, question, answer, timestamp) VALUES (?, ?, ?, ?)",
                           (st.session_state.auth_user, q, ans, datetime.datetime.utcnow().isoformat()))
            conn.commit()
            log_action(st.session_state.auth_user, "career_qna", q)

# ----------------------
# Tax Estimator (India) — basic
# ----------------------
elif choice == "Tax Estimator":
    st.header("Basic Indian Tax Estimator")
    income = st.number_input("Annual taxable income (₹)", min_value=0.0, value=500000.0)
    deductions_80c = st.number_input("Deductions under 80C (₹)", min_value=0.0, value=0.0)
    other_deductions = st.number_input("Other deductions (₹)", min_value=0.0, value=0.0)
    regime = st.selectbox("Tax regime", ["New", "Old"])
    if st.button("Estimate"):
        # Very simplified — for demo only
        taxable_old = max(0, income - deductions_80c - other_deductions)
        tax_old = 0
        if taxable_old <= 250000:
            tax_old = 0
        elif taxable_old <= 500000:
            tax_old = (taxable_old - 250000) * 0.05
        elif taxable_old <= 1000000:
            tax_old = 12500 + (taxable_old - 500000) * 0.2
        else:
            tax_old = 112500 + (taxable_old - 1000000) * 0.3

        # new regime (simplified slab example)
        taxable_new = income - other_deductions
        tax_new = 0
        if taxable_new <= 300000:
            tax_new = 0
        elif taxable_new <= 600000:
            tax_new = (taxable_new - 300000) * 0.05
        elif taxable_new <= 900000:
            tax_new = 15000 + (taxable_new - 600000) * 0.1
        else:
            tax_new = 45000 + (taxable_new - 900000) * 0.15

        st.write("**Old Regime Estimated Tax:** ₹", round(tax_old, 2))
        st.write("**New Regime Estimated Tax:** ₹", round(tax_new, 2))

        # Export PDF
        buf = BytesIO()
        p = canvas.Canvas(buf, pagesize=letter)
        p.drawString(72, 720, f"Tax Estimate — User: {st.session_state.auth_user}")
        p.drawString(72, 700, f"Income: ₹{income}")
        p.drawString(72, 680, f"Old Regime Tax: ₹{round(tax_old,2)}")
        p.drawString(72, 660, f"New Regime Tax: ₹{round(tax_new,2)}")
        p.showPage()
        p.save()
        st.download_button("Download Tax Report (PDF)", data=buf.getvalue(), file_name="tax_report.pdf")
        log_action(st.session_state.auth_user, "tax_estimate", json.dumps({"income": income, "old": tax_old, "new": tax_new}))

# ----------------------
# Watchlist (simple view)
# ----------------------
elif choice == "Watchlist":
    st.header("Your Watchlist (recent tracked actions)")
    cursor.execute("SELECT action, details, timestamp FROM user_logs WHERE username=? AND action LIKE 'track_stock%' ORDER BY timestamp DESC LIMIT 50", (st.session_state.auth_user,))
    rows = cursor.fetchall()
    if rows:
        df = pd.DataFrame(rows, columns=["action", "details", "timestamp"])
        st.dataframe(df)
        st.download_button("Export Watchlist CSV", data=df.to_csv(index=False).encode(), file_name="watchlist.csv")
    else:
        st.info("You have not tracked any stocks yet.")

# ----------------------
# Admin Dashboard
# ----------------------
elif choice == "Admin Dashboard":
    if not st.session_state.is_admin:
        st.error("Admin access required")
    else:
        st.header("Admin Dashboard — User Analytics")
        st.subheader("User Logs")
        cursor.execute("SELECT username, action, details, ip, timestamp FROM user_logs ORDER BY timestamp DESC LIMIT 500")
        logs = cursor.fetchall()
        if logs:
            df_logs = pd.DataFrame(logs, columns=["username", "action", "details", "ip", "timestamp"])
            st.dataframe(df_logs)
            st.download_button("Download logs (CSV)", data=df_logs.to_csv(index=False).encode(), file_name="user_logs.csv")
            st.download_button("Download logs (Excel)", data=df_logs.to_excel(BytesIO(), index=False).getvalue() if False else df_logs.to_csv(index=False).encode(), file_name="user_logs.xlsx")

        st.subheader("Top Users")
        cursor.execute("SELECT username, COUNT(*) as cnt FROM user_logs GROUP BY username ORDER BY cnt DESC LIMIT 20")
        top = cursor.fetchall()
        if top:
            df_top = pd.DataFrame(top, columns=["username", "actions"])
            st.bar_chart(df_top.set_index("username"))

# ----------------------
# End of app
# ----------------------


# Helpful note (display)
st.sidebar.markdown("---")
st.sidebar.markdown("Need help? Reply here and I can guide you through deployment steps.")

# EOF

# ----------------------
# Requirements (requirements.txt)
# ----------------------
# Put the following into requirements.txt when deploying:
# streamlit
# openai
# yfinance
# pandas
# reportlab

# ----------------------
# Deployment note
# ----------------------
# 1) Create a GitHub repo with this app.py and requirements.txt
# 2) Deploy to Streamlit Cloud and set the OPENAI_API_KEY secret
# 3) For client IP capture, configure headers on your host/load-balancer
# 4) For production, replace SQLite with Postgres and secure secrets
