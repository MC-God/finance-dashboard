import asyncio
from telegram import Update
from telegram.ext import ContextTypes
import os
import json
import datetime
from dotenv import load_dotenv
import google.generativeai as genai
from src.sheets_client import get_sheet_client

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
genai.configure(api_key=GEMINI_API_KEY)

# (start_command, ai_report_command, send_portfolio_status 함수는 기존과 동일하게 유지)
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_msg = "안녕하세요! AI 투자 어시스턴트입니다.\n\n👇 아래 명령어와 자연어를 사용해 보세요.\n- /ai : 오늘의 4인방 AI 심층 분석 리포트 확인\n- 자산 조회: '지금 내 자산현황 알려줘', '포트폴리오 보여줘'\n- 매매 기록: '오늘 테슬라 10주 170불에 매수했어'"
    await update.message.reply_text(welcome_msg)

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
                shares, c_price, d_return = row.get("Shares", 0), row.get("Current_Price", 0), row.get("1D_Return", 0)
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
        # 안정화된 방식으로 JSON 추출 강제
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_text)
        intent = data.get("intent", "unknown")
        
        if intent == "view_portfolio":
            await send_portfolio_status(update)
        elif intent == "record_transaction":
            if not data.get("ticker") or not data.get("action"):
                 await update.message.reply_text("종목명이나 액션이 누락되었습니다. 다시 말씀해주세요!")
                 return
            today_date = datetime.datetime.now().strftime("%Y-%m-%d")
            sheet_client = get_sheet_client()
            doc = sheet_client.open_by_key(SPREADSHEET_ID)
            tx_sheet = doc.worksheet("Transaction")
            new_row = [today_date, data["action"], data["ticker"], data.get("shares", 0), data.get("price", 0)]
            tx_sheet.append_row(new_row)
            await update.message.reply_text(f"✅ 시트 기록 완료!\n[{data['action']}] {data['ticker']} {data.get('shares')}주 (단가: {data.get('price')})")
        else:
            await update.message.reply_text("무슨 말씀인지 잘 모르겠어요. 다시 말씀해주세요!")
    except Exception as e:
        await update.message.reply_text(f"처리 중 오류가 발생했습니다: {e}")