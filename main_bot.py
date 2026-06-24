import os
import json
import re
import datetime
import asyncio
import gspread
import pandas as pd
import requests
import yfinance as yf
from functools import wraps
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from dotenv import load_dotenv
from google import genai
from google.genai import types
from src.sheets_client import get_sheet_client

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
ai_client = genai.Client(api_key=GEMINI_API_KEY)
ALLOWED_USER_IDS = [int(uid.strip()) for uid in os.getenv("ALLOWED_USER_IDS", "").split(",") if uid.strip()]
DASHBOARD_URL = "https://finance-dashboard-mcgod.streamlit.app"

# ----------------- 방어 로직 및 권한 -----------------
def restricted(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id if update.effective_user else None
        if ALLOWED_USER_IDS and user_id not in ALLOWED_USER_IDS:
            if update.message: await update.message.reply_text("⛔ [보안 차단] 허가되지 않은 사용자입니다.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

def extract_json_from_text(text: str):
    cleaned = re.sub(r'```json\n|```', '', text).strip()
    match = re.search(r'(\[.*\]|\{.*\})', cleaned, re.DOTALL)
    if match: return json.loads(match.group(1))
    return json.loads(cleaned)

# ----------------- 능동형 스케줄러 (급등/급락/익절/손절 알람) -----------------
async def monitor_portfolio_alerts(context: ContextTypes.DEFAULT_TYPE):
    """지정된 주기마다 포트폴리오의 실시간 가격을 체크하여 손절/익절 알림을 보냅니다."""
    # 하드코딩된 손절/익절 임계치 (필요시 .env로 분리 가능)
    TAKE_PROFIT_PCT = 20.0
    STOP_LOSS_PCT = -10.0
    
    print(f"[{datetime.datetime.now()}] 실시간 포트폴리오 위험 모니터링 실행 중...")
    try:
        doc = get_sheet_client().open_by_key(SPREADSHEET_ID)
        records = doc.worksheet("Portfolio").get_all_records()
        if not records: return
        
        alerts = []
        for row in records:
            ticker = str(row.get("Ticker", "")).replace("'", "").strip()
            avg_price = float(str(row.get("Avg_Price", 0)).replace(",", ""))
            if not ticker or avg_price <= 0: continue
            
            # 실시간 시세 조회 로직
            current_price = avg_price
            is_kr = ticker.isdigit() or len(ticker) == 6
            try:
                if is_kr:
                    url = f"https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{ticker}"
                    res = requests.get(url, timeout=5).json()
                    current_price = float(res['result']['areas'][0]['datas'][0]['nv'])
                else:
                    df_stock = yf.Ticker(ticker).history(period="1d")
                    if not df_stock.empty: current_price = float(df_stock['Close'].iloc[-1])
            except Exception as e:
                continue # 시세 조회 실패 시 스킵
            
            # 수익률 계산
            roi = ((current_price - avg_price) / avg_price) * 100
            
            # 알람 조건 판별 및 캐싱 처리 (중복 알림 방지)
            alert_key = f"{ticker}_{datetime.date.today()}"
            if "alerted" not in context.bot_data: context.bot_data["alerted"] = set()
            
            if roi >= TAKE_PROFIT_PCT and f"{alert_key}_TP" not in context.bot_data["alerted"]:
                alerts.append(f"🚀 **[익절 구간 도달]** {ticker}\n현재 수익률: **+{roi:.2f}%** (목표치 +{TAKE_PROFIT_PCT}%)")
                context.bot_data["alerted"].add(f"{alert_key}_TP")
            elif roi <= STOP_LOSS_PCT and f"{alert_key}_SL" not in context.bot_data["alerted"]:
                alerts.append(f"🚨 **[손절 라인 이탈]** {ticker}\n현재 수익률: **{roi:.2f}%** (위험치 {STOP_LOSS_PCT}%)")
                context.bot_data["alerted"].add(f"{alert_key}_SL")

        if alerts and ALLOWED_USER_IDS:
            msg = "🔔 **[포트폴리오 리스크 레이더]**\n\n" + "\n\n".join(alerts)
            for uid in ALLOWED_USER_IDS:
                await context.bot.send_message(chat_id=uid, text=msg, parse_mode="Markdown")
                
    except Exception as e:
        print(f"모니터링 오류: {e}")

# ----------------- 일반 핸들러 -----------------
@restricted
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "안녕하세요! 프라이빗 AI 투자 어시스턴트입니다.\n👇 아래 버튼을 눌러 대시보드를 확인하거나, '애플 10주 200달러에 매도'와 같이 자연어로 매매를 기록해 보세요!"
    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📈 대시보드 열기", url=DASHBOARD_URL)]]))

@restricted
async def ai_report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("데이터를 불러오는 중입니다... 🔄")
    try:
        records = get_sheet_client().open_by_key(SPREADSHEET_ID).worksheet("AI_Reports").get_all_records()
        if not records: return await update.message.reply_text("아직 작성된 리포트가 없습니다.")
        latest = records[-1]
        await update.message.reply_text(f"📅 기준일: {latest.get('Date', 'N/A')}\n\n🤖 AI 심층 리포트 전송 시작...")
        for key, name in [('Quant_Opinion', '📉 [퀀트]'), ('Macro_Opinion', '🌍 [매크로]'), ('Value_Opinion', '💎 [가치투자]'), ('Ten_Bagger_Opinion', '🚀 [텐베거]')]:
            if latest.get(key):
                await update.message.reply_text(f"{name}\n{latest.get(key)}")
                await asyncio.sleep(0.5)
    except Exception as e:
        await update.message.reply_text(f"오류: {e}")

@restricted
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await update.message.reply_text("🤖 의도를 분석 중입니다...")
    prompt = f"""
    사용자 입력을 분석해 JSON 반환. 한국 주식은 6자리 숫자, 미국 주식은 영문 대문자 티커.
    {{ "intent": "view_portfolio" OR "record_transaction" OR "unknown", "action": "매수" OR "매도", "ticker": "...", "currency": "KRW" OR "USD", "shares": 수량, "price": 단가 }}
    입력: "{user_text}"
    """
    try:
        res = ai_client.models.generate_content(model='gemini-3.5-flash', contents=prompt, config=types.GenerateContentConfig(response_mime_type="application/json"))
        data = extract_json_from_text(res.text)
        if isinstance(data, list): data = data[0] if data else {}
        
        intent = data.get("intent", "unknown")
        if intent == "record_transaction":
            if not data.get("ticker"): return await update.message.reply_text("정보가 부족합니다.")
            action_type, ticker, shares, price, currency = data["action"], data["ticker"], data.get("shares", 0), data.get("price", 0), data.get("currency", "KRW")
            doc = get_sheet_client().open_by_key(SPREADSHEET_ID)
            doc.worksheet("Transaction").append_row([datetime.datetime.now().strftime("%Y-%m-%d"), action_type, ticker, shares, price, "일반", currency])
            
            reply = f"✅ [{action_type}] {ticker} {shares}주 (단가: {price:,}{'원' if currency=='KRW' else '$'}) 기록 완료!"
            if action_type in ["매도", "sell"]:
                avg_price = 0
                for r in doc.worksheet("Portfolio").get_all_records():
                    if str(r.get("Ticker", "")).replace("'", "").strip() == ticker:
                        avg_price = float(str(r.get("Avg_Price", "0")).replace(",", "")); break
                if avg_price > 0:
                    realized = (price - avg_price) * shares
                    try: pnl_sheet = doc.worksheet("Realized_PnL")
                    except: pnl_sheet = doc.add_worksheet(title="Realized_PnL", rows="1000", cols="10")
                    pnl_sheet.append_row([datetime.datetime.now().strftime("%Y-%m-%d"), ticker, "일반", currency, shares, price, avg_price, realized])
                    reply += f"\n💰 실현 손익: {'+' if realized>0 else ''}{realized:,.2f} (평단: {avg_price:,.2f} 기준)"
            await update.message.reply_text(reply, parse_mode="Markdown")
        else: await update.message.reply_text("이해하지 못했습니다.")
    except Exception as e: await update.message.reply_text(f"오류: {e}")

def main():
    if not TELEGRAM_TOKEN: return print("❌ 텔레그램 토큰이 없습니다.")
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # 주기적 백그라운드 작업 등록 (2시간(7200초)마다 모니터링 실행)
    application.job_queue.run_repeating(monitor_portfolio_alerts, interval=7200, first=10)
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("ai", ai_report_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ 봇 가동 시작 및 리스크 모니터링 스케줄러 등록 완료!")
    application.run_polling()

if __name__ == '__main__':
    main()
