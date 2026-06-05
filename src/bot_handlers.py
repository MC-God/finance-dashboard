import asyncio
from telegram import Update
from telegram.ext import ContextTypes
import os
import json
import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types
from src.sheets_client import get_sheet_client

# 환경변수 및 API 클라이언트 로드
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
ai_client = genai.Client(api_key=GEMINI_API_KEY)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """봇을 처음 시작할 때의 안내 메시지"""
    welcome_msg = (
        "안녕하세요! AI 투자 어시스턴트입니다.\n\n"
        "👇 아래 명령어와 자연어를 사용해 보세요.\n"
        "- /ai : 오늘의 4인방 AI 심층 분석 리포트 확인\n"
        "- 자산 조회: '지금 내 자산현황 알려줘', '포트폴리오 보여줘'\n"
        "- 매매 기록: '오늘 테슬라 10주 170불에 매수했어'"
    )
    await update.message.reply_text(welcome_msg)

async def ai_report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """구글 시트에서 가장 최근 AI 리포트를 읽어와서 나누어 전송"""
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
        
        if latest.get('Quant_Opinion'):
            await update.message.reply_text(f"📉 [퀀트 의견]\n{latest.get('Quant_Opinion')}")
            await asyncio.sleep(0.5)
            
        if latest.get('Macro_Opinion'):
            await update.message.reply_text(f"🌍 [매크로 의견]\n{latest.get('Macro_Opinion')}")
            await asyncio.sleep(0.5)
            
        if latest.get('Value_Opinion'):
            await update.message.reply_text(f"💎 [가치투자 의견]\n{latest.get('Value_Opinion')}")
            await asyncio.sleep(0.5)
            
        if latest.get('Ten_Bagger_Opinion'):
            await update.message.reply_text(f"🚀 [텐베거 의견]\n{latest.get('Ten_Bagger_Opinion')}")

    except Exception as e:
        await update.message.reply_text(f"오류가 발생했습니다: {e}")

async def send_portfolio_status(update: Update):
    """구글 시트의 Portfolio 탭을 읽어와 자산 현황을 요약 전송"""
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
            shares = row.get("Shares", 0)
            c_price = row.get("Current_Price", 0)
            d_return = row.get("1D_Return", 0)
            
            if ticker:
                # 수익률이 양수면 🔴, 음수면 🔵 아이콘 추가 (한국 스타일)
                icon = "🔴" if float(d_return) > 0 else "🔵" if float(d_return) < 0 else "⚪"
                msg += f"▪️ **{ticker}** : {shares}주\n"
                msg += f"   (현재가: {c_price} / 1D: {icon} {d_return}%)\n\n"
                
        await update.message.reply_text(msg, parse_mode="Markdown")
        
    except Exception as e:
        await update.message.reply_text(f"포트폴리오 조회 중 오류가 발생했습니다: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """자연어를 분석하여 의도(Intent)에 따라 자산 조회 또는 매매 기록 수행"""
    user_text = update.message.text
    await update.message.reply_text("🤖 입력하신 내용을 분석 중입니다...")
    
    # 의도 파악(Intent Classification)을 포함한 프롬프트
    prompt = f"""
    사용자의 입력을 분석하여 의도(intent)를 파악하고, 결과를 오직 JSON 형식으로만 반환해.
    입력: "{user_text}"
    
    JSON 스키마:
    {{
        "intent": "view_portfolio" (자산을 조회하거나 보여달라고 할 때) OR "record_transaction" (특정 주식을 매수/매도했다고 할 때) OR "unknown" (둘 다 아닐 때),
        "action": "매수" 또는 "매도" (매매일 경우에만 작성, 아니면 null),
        "ticker": "주식 티커 (예: AAPL, NVDA, 005930)" (매매일 경우에만 작성, 아니면 null),
        "shares": 수량 (매매일 경우에만 작성, 숫자),
        "price": 단가 (매매일 경우에만 작성, 숫자)
    }}
    """
    
    try:
        response = ai_client.models.generate_content(
            model='gemini-3.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        
        # 만약 모델이 마크다운 블록(```json)을 포함해 반환할 경우를 대비한 클렌징
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_text)
        
        intent = data.get("intent", "unknown")
        
        # 1. 자산 조회 의도일 경우
        if intent == "view_portfolio":
            await send_portfolio_status(update)
            
        # 2. 매매 기록 의도일 경우
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
                f"✅ 구글 시트 [Transaction] 탭에 정상 기록되었습니다!\n"
                f"[{data['action']}] {data['ticker']} {data.get('shares')}주 (단가: {data.get('price')})"
            )
            
        # 3. 그 외 알 수 없는 입력일 경우
        else:
            await update.message.reply_text("무슨 말씀인지 잘 모르겠어요. '자산현황 보여줘' 또는 '엔비디아 5주 샀어' 처럼 말씀해주세요!")
            
    except Exception as e:
        await update.message.reply_text(f"처리 중 오류가 발생했습니다: {e}")
