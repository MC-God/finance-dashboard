import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
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

DASHBOARD_URL = "https://본인의-스트림릿-주소.streamlit.app"

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_msg = (
        "안녕하세요! AI 투자 어시스턴트입니다.\n\n"
        "👇 아래 버튼을 눌러 대시보드를 확인하거나 명령어를 입력해 보세요.\n"
        "- /ai : 오늘의 4인방 AI 심층 분석 리포트 확인\n"
        "📸 보유 주식 현황 스크린샷을 보내주시면 자동으로 판독하여 시트에 입력해 드립니다!"
    )
    keyboard = [[InlineKeyboardButton("📈 내 포트폴리오 대시보드 열기", url=DASHBOARD_URL)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(welcome_msg, reply_markup=reply_markup)

# --- 📸 신규 기능: 이미지 캡처본 분석 핸들러 ---
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 이미지를 분석 중입니다... 잠시만 기다려주세요 (약 5~10초 소요)")
    
    try:
        # 텔레그램 서버에서 이미지 파일 다운로드
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        # 멀티모달 프롬프트 구성
        prompt = """
        첨부된 주식 보유 현황 스크린샷에서 종목 정보들을 정확하게 추출해줘.
        추출할 정보: 종목명 또는 티커(ticker), 보유 주식 수량(shares), 평균 매입 단가(price)
        
        출력은 반드시 다른 부가 설명 없이 오직 아래 스키마의 JSON 배열 형태로만 반환해줘.
        [
            {"ticker": "AAPL", "shares": 10, "price": 175.5},
            {"ticker": "005930", "shares": 50, "price": 72000}
        ]
        """
        
        # Gemini Vision 분석 요청
        response = ai_client.models.generate_content(
            model='gemini-3.5-flash',
            contents=[
                types.Part.from_bytes(data=bytes(photo_bytes), mime_type="image/jpeg"),
                prompt
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        
        parsed_stocks = json.loads(response.text)
        
        if not parsed_stocks:
            await update.message.reply_text("❌ 이미지에서 주식 보유 정보를 찾지 못했습니다. 화질을 확인하거나 직접 텍스트로 입력해 주세요.")
            return
            
        # 임시 보관함에 파싱 데이터 저장 (사용자 컨텍스트 활용)
        context.user_data['temp_ocr_data'] = parsed_stocks
        
        # 사용자에게 파싱 결과 확인 메시지 유도
        confirm_msg = "🔍 **[이미지 분석 완료 결과]**\n\n"
        for idx, stock in enumerate(parsed_stocks, 1):
            confirm_msg += f"{idx}. **{stock['ticker']}** : {stock['shares']}주 (평단: {stock['price']:,}원)\n"
            
        confirm_msg += "\n위 데이터가 정확한가요? 저장할 계좌 종류를 선택하시면 구글 시트에 일괄 대량 입력됩니다."
        
        # 인라인 버튼 제공 (일반/연금 선택)
        keyboard = [
            [
                InlineKeyboardButton("📁 일반 계좌에 저장", callback_data="save_ocr_일반"),
                InlineKeyboardButton("🛡️ 연금 계좌에 저장", callback_data="save_ocr_연금")
            ],
            [InlineKeyboardButton("❌ 취소", callback_data="save_ocr_cancel")]
        ]
        await update.message.reply_text(confirm_msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        
    except Exception as e:
        await update.message.reply_text(f"❌ 이미지 파싱 중 오류가 발생했습니다: {e}")

# --- 버튼 클릭 처리 핸들러 (Callback Query) ---
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if not data.startswith("save_ocr_"):
        return
        
    action = data.replace("save_ocr_", "")
    
    if action == "cancel":
        context.user_data.pop('temp_ocr_data', None)
        await query.edit_message_text("❌ 입력 작업이 취소되었습니다.")
        return
        
    stocks = context.user_data.get('temp_ocr_data')
    if not stocks:
        await query.edit_message_text("❌ 만료된 세션이거나 저장할 데이터가 존재하지 않습니다.")
        return
        
    try:
        await query.edit_message_text(f"📥 구글 시트({action} 계좌)에 일괄 기록 중...")
        
        today_date = datetime.datetime.now().strftime("%Y-%m-%d")
        sheet_client = get_sheet_client()
        doc = sheet_client.open_by_key(SPREADSHEET_ID)
        tx_sheet = doc.worksheet("Transaction")
        
        # 시트에 한 줄씩 대량 누적 입력
        for stock in stocks:
            new_row = [today_date, "매수", stock["ticker"], stock.get("shares", 0), stock.get("price", 0), action]
            tx_sheet.append_row(new_row)
            
        context.user_data.pop('temp_ocr_data', None)
        await query.edit_message_text(f"✅ 성공적으로 총 {len(stocks)}개의 종목 데이터가 **[{action} 계좌]** 트랜잭션 시트에 반영되었습니다!")
        
    except Exception as e:
        await query.edit_message_text(f"❌ 구글 시트 저장 중 예외 발생: {e}")

# --- (기존의 명령어 핸들러 코드 유지) ---
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
                account_type = row.get("Account", "일반")
                try:
                    val = float(str(d_return).replace("%", "").strip())
                    icon = "🔴" if val > 0 else "🔵" if val < 0 else "⚪"
                except ValueError:
                    icon = "⚪"
                msg += f"▪️ **{ticker}** ({account_type}) : {shares}주\n   (현재가: {c_price} / 1D: {icon} {d_return}%)\n\n"
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
            # 텍스트 입력 시에는 기본적으로 '일반' 계좌로 들어가도록 설정 (자연어 기입 가능 시 연동 확장 가능)
            new_row = [today_date, data["action"], data["ticker"], data.get("shares", 0), data.get("price", 0), "일반"]
            tx_sheet.append_row(new_row)
            await update.message.reply_text(f"✅ 구글 시트 기록 완료!\n[{data['action']}] {data['ticker']} {data.get('shares')}주 (단가: {data.get('price')})")
        else:
            await update.message.reply_text("무슨 말씀인지 잘 모르겠어요. 다시 말씀해주세요!")
    except Exception as e:
        await update.message.reply_text(f"처리 중 오류가 발생했습니다: {e}")
