import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
# --- 텔레그램 내장 웹뷰를 위한 라이브러리 추가 ---
from telegram import WebAppInfo 
import os
import json
import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types
from src.sheets_client import get_sheet_client

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# 본인의 Streamlit 대시보드 주소를 여기에 넣으세요! (반드시 https:// 로 시작해야 합니다)
DASHBOARD_URL = "https://본인의-스트림릿-주소.streamlit.app"

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_msg = (
        "안녕하세요! AI 투자 어시스턴트입니다.\n\n"
        "👇 아래 버튼을 눌러 대시보드를 확인하거나 명령어를 입력해 보세요.\n"
        "- /ai : 오늘의 4인방 AI 심층 분석 리포트 확인\n"
        "- 자산 조회: '지금 내 자산현황 알려줘'\n"
        "- 매매 기록: '오늘 테슬라 10주 170불에 매수했어'"
    )
    
    # 텔레그램 메시지 아래에 예쁜 버튼(Inline Keyboard) 만들기
    keyboard = [
        # 방법 A: 텔레그램 앱 내부에서 팝업으로 열기 (가장 추천하는 깔끔한 방식)
        [InlineKeyboardButton("📈 내 포트폴리오 대시보드 열기", web_app=WebAppInfo(url=DASHBOARD_URL))],
        
        # 방법 B: 일반 인터넷 브라우저 앱(사파리/크롬)으로 열기 원할 경우 (참고용)
        # [InlineKeyboardButton("🌐 외부 브라우저에서 대시보드 열기", url=DASHBOARD_URL)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # 메시지와 함께 버튼을 전송
    await update.message.reply_text(welcome_msg, reply_markup=reply_markup)

async def ai_report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("데이터를 불러오는 중입니다... 🔄")
    try:
        sheet_client = get_sheet_client()
        doc = sheet_client.open_by_key(SPREADSHEET_ID)
        ai_records = doc.worksheet("AI_Reports").get_all_records()
        
        if not ai_records:
            await update.message.reply_text("아직 작성된 AI 리포트가 없습니다.")
            return
            
        latest = ai_records[-1] 
        await update.message.reply_text(f"📅 분석 일자: {latest.get('Date', 'N/A')}\n\n🤖 4인방 AI 심층 분석 리포트를 순차적으로 전송합니다.")
        await asyncio.sleep(0.5) 
        
        for key, name in [('Quant_Opinion', '📉 [퀀트 의견]'), ('Macro_Opinion', '🌍 [매크로 의견]'), ('Value_Opinion', '💎 [가치투자 의견]'), ('Ten_Bagger_Opinion', '🚀 [텐베거 의견]')]:
            if latest.get(key):
                await update.message.reply_text(f"{name}\n{latest.get(key)}")
                await asyncio.sleep(0.5)

    except Exception as e:
        await update.message.reply_text(f"오류가 발생했습니다: {e}")

async def send_portfolio_status(update: Update):
    try:
        sheet_client = get_sheet_client()
        doc = sheet_client.open_by_key(SPREADSHEET_ID)
        portfolio_records = doc.worksheet("Portfolio").get_all_records()
        
        if not portfolio_records:
            await update.message.reply_text("현재 포트폴리오에 등록된 종목이 없습니다.")
            return
            
        msg = "📊 **[현재 자산 현황 요약]**\n\n"
        for row in portfolio_records:
            ticker = row.get("Ticker")
            if ticker:
                shares = row.get("Shares", 0)
                c_price = row.get("Current_Price", 0)
                d_return = row.get("1D_Return", 0)
                icon = "🔴" if float(d_return) > 0 else "🔵" if float(d_return) < 0 else "⚪"
                msg += f"▪️ **{ticker}** : {shares}주\n   (현재가: {c_price} / 1D: {icon} {d_return}%)\n\n"
                
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"포트폴리오 조회 중 오류가 발생했습니다: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await update.message.reply_text("🤖 입력하신 내용을 분석 중입니다...")
    
    prompt = f"""
    사용자의 입력을 분석하여 의도(intent)를 파악하고, 결과를 오직 JSON 형식으로만 반환해.
    입력: "{user_text}"
    
    JSON 스키마:
    {{
        "intent": "view_portfolio" OR "record_transaction" OR "unknown",
        "action": "매수" 또는 "매도",
        "ticker": "주식 티커 (예: AAPL, NVDA, 005930)",
        "shares": 수량 (숫자),
        "price": 단가 (숫자)
    }}
    """
    
    try:
        response = ai_client.models.generate_content(
            model='gemini-3.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        
        data = json.loads(response.text)
        intent = data.get("intent", "unknown")
        
        if intent == "view_portfolio":
            await send_portfolio_status(update)
            
        elif intent == "record_transaction":
            if not data.get("ticker") or not data.get("action"):
                 await update.message.reply_text("매매 기록으로 인식되었으나 종목명이나 액션이 누락되었습니다. 다시 말씀해주세요!")
                 return
                 
            today_date = datetime.datetime.now().strftime("%Y-%m-%d")
            sheet_client = get_sheet_client()
            doc = sheet_client.open_by_key(SPREADSHEET_ID)
            tx_sheet = doc.worksheet("Transaction")
            
            new_row = [today_date, data["action"], data["ticker"], data.get("shares", 0), data.get("price", 0)]
            tx_sheet.append_row(new_row)
            
            await update.message.reply_text(
                f"✅ 구글 시트 기록 완료!\n"
                f"[{data['action']}] {data['ticker']} {data.get('shares')}주 (단가: {data.get('price')})"
            )
            
        else:
            await update.message.reply_text("무슨 말씀인지 잘 모르겠어요. 다시 말씀해주세요!")
            
    except Exception as e:
        await update.message.reply_text(f"처리 중 오류가 발생했습니다: {e}")
