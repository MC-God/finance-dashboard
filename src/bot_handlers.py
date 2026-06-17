import os
import json
import re
import datetime
import asyncio
import gspread
from functools import wraps
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from dotenv import load_dotenv
from google import genai
from google.genai import types
from src.sheets_client import get_sheet_client

# 환경변수 로드
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# 허용된 사용자 ID 리스트 파싱
ALLOWED_USER_IDS = [
    int(uid.strip()) for uid in os.getenv("ALLOWED_USER_IDS", "").split(",") if uid.strip()
]

DASHBOARD_URL = "https://finance-dashboard-mcgod.streamlit.app"

def restricted(func):
    """지정된 USER_ID만 봇을 사용할 수 있도록 막는 보안 데코레이터"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if ALLOWED_USER_IDS and user_id not in ALLOWED_USER_IDS:
            if update.message:
                await update.message.reply_text("⛔ [보안 차단] 허가되지 않은 사용자입니다.")
            elif update.callback_query:
                await update.callback_query.answer("⛔ 권한이 없습니다.", show_alert=True)
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

def extract_json_from_text(text: str):
    """AI 응답 텍스트에서 정규식을 이용해 순수 JSON 데이터만 안전하게 추출"""
    cleaned = re.sub(r'```json\n|```', '', text).strip()
    match = re.search(r'(\[.*\]|\{.*\})', cleaned, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    return json.loads(cleaned)

@restricted
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_msg = (
        "안녕하세요! 프라이빗 AI 투자 어시스턴트입니다.\n\n"
        "👇 아래 버튼을 눌러 대시보드를 확인하거나 명령어를 입력해 보세요.\n"
        "- /ai : 오늘의 4인방 AI 심층 분석 리포트 확인\n"
        "📸 보유 주식 현황 스크린샷을 보내주시면 자동으로 판독하여 시트에 입력해 드립니다!"
    )
    keyboard = [[InlineKeyboardButton("📈 내 포트폴리오 대시보드 열기", url=DASHBOARD_URL)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(welcome_msg, reply_markup=reply_markup)

@restricted
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 이미지를 분석하여 표준 코드로 변환 중입니다... (약 5~10초 소요)")
    
    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        prompt = """
        첨부된 주식 보유 현황 스크린샷에서 종목 정보들을 정확하게 추출해줘.
        ⚠️ [필수 변환 규칙]
        1. ticker: FinanceDataReader가 인식할 수 있는 표준 코드로 변환해야 해.
           - 한국 주식: 반드시 6자리 숫자 종목코드 (예: 삼성전자는 "005930")
           - 미국 주식: 반드시 영문 대문자 티커 기호 (예: Apple은 "AAPL")
        2. currency: 해당 주식의 거래 통화를 판별해줘.
           - 한국 주식 상장이면 "KRW"
           - 미국 주식 상장이면 "USD"
        3. shares: 보유 주식 수량 (숫자)
        4. price: 평균 매입 단가 (숫자)
        
        출력은 반드시 다른 부가 설명 없이 오직 아래 스키마의 JSON 배열 형태로만 반환해줘.
        [
            {"ticker": "005930", "currency": "KRW", "shares": 50, "price": 72000},
            {"ticker": "TSLA", "currency": "USD", "shares": 10, "price": 175.5}
        ]
        """
        
        response = ai_client.models.generate_content(
            model='gemini-3.5-flash',
            contents=[types.Part.from_bytes(data=bytes(photo_bytes), mime_type="image/jpeg"), prompt],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        
        parsed_stocks = extract_json_from_text(response.text)
        
        # [방어 로직] AI가 리스트가 아닌 단일 딕셔너리로 반환했을 경우를 대비
        if isinstance(parsed_stocks, dict):
            parsed_stocks = [parsed_stocks]
        
        if not parsed_stocks:
            await update.message.reply_text("❌ 이미지에서 주식 보유 정보를 찾지 못했습니다.")
            return
            
        context.user_data['temp_ocr_data'] = parsed_stocks
        
        confirm_msg = "🔍 **[표준 코드 변환 판독 결과]**\n\n"
        for idx, stock in enumerate(parsed_stocks, 1):
            unit = "원" if stock['currency'] == "KRW" else "$"
            confirm_msg += f"{idx}. **{stock['ticker']}** ({stock['currency']}) : {stock['shares']}주 (평단: {stock['price']:,}{unit})\n"
            
        confirm_msg += "\n위 데이터가 정확한가요? 저장할 계좌 종류를 선택하시면 구글 시트에 일괄 입력됩니다."
        
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

@restricted
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
        await query.edit_message_text("❌ 저장할 데이터가 존재하지 않습니다.")
        return
    
    try:
        await query.edit_message_text(f"📥 구글 시트({action} 계좌)에 표준 데이터 기록 중...")
        
        today_date = datetime.datetime.now().strftime("%Y-%m-%d")
        sheet_client = get_sheet_client()
        doc = sheet_client.open_by_key(SPREADSHEET_ID)
        tx_sheet = doc.worksheet("Transaction")
        
        for stock in stocks:
            new_row = [
                today_date, 
                "매수", 
                stock["ticker"], 
                stock.get("shares", 0), 
                stock.get("price", 0), 
                action,    
                stock.get("currency", "KRW")   
            ]
            tx_sheet.append_row(new_row)
            
        context.user_data.pop('temp_ocr_data', None)
        await query.edit_message_text(f"✅ 성공적으로 총 {len(stocks)}개의 종목이 정상 규격으로 **[{action} 계좌]**에 반영되었습니다!")
        
    except Exception as e:
        await query.edit_message_text(f"❌ 구글 시트 저장 중 예외 발생: {e}")

@restricted
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await update.message.reply_text("🤖 입력하신 내용을 분석 중입니다...")
    
    prompt = f"""
    사용자의 입력을 분석하여 의도(intent)를 파악하고, 결과를 오직 JSON 형식으로만 반환해.
    ⚠️ [필수 변환 규칙]
    1. ticker: 한국 주식은 6자리 숫자 코드, 미국 주식은 영문 대문자 티커로 변환해.
    2. currency: 한국 주식이면 "KRW", 미국 주식이면 "USD"로 판별해.
    
    입력: "{user_text}"
    
    JSON 스키마:
    {{
        "intent": "view_portfolio" OR "record_transaction" OR "unknown",
        "action": "매수" 또는 "매도",
        "ticker": "표준 주식 티커/코드",
        "currency": "KRW" OR "USD",
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
        
        data = extract_json_from_text(response.text)
        
        # [방어 로직] AI가 JSON 객체가 아닌 JSON 배열 [ {...} ] 형태로 반환했을 경우 처리
        if isinstance(data, list):
            data = data[0] if data else {}
            
        intent = data.get("intent", "unknown")
        
        if intent == "view_portfolio":
            await send_portfolio_status(update)
            
        elif intent == "record_transaction":
            if not data.get("ticker") or not data.get("action"):
                 await update.message.reply_text("매매 기록으로 인식되었으나 핵심 정보가 누락되었습니다.")
                 return
                 
            today_date = datetime.datetime.now().strftime("%Y-%m-%d")
            sheet_client = get_sheet_client()
            doc = sheet_client.open_by_key(SPREADSHEET_ID)
            
            action_type = data["action"]
            ticker = data["ticker"]
            shares = data.get("shares", 0)
            price = data.get("price", 0)
            currency = data.get("currency", "KRW")
            account_type = "일반" # 기본값 처리
            unit = "원" if currency == "KRW" else "$"
            
            # 1. Transaction 시트에 기본 기록
            tx_sheet = doc.worksheet("Transaction")
            tx_sheet.append_row([today_date, action_type, ticker, shares, price, account_type, currency])
            
            reply_text = f"✅ 구글 시트 거래 기록 완료!\n[{action_type}] {ticker} {shares}주 (단가: {price:,}{unit})"
            
            # 2. 매도일 경우 Realized_PnL (실현 손익) 계산 및 기록
            if action_type in ["매도", "sell"]:
                try:
                    port_records = doc.worksheet("Portfolio").get_all_records()
                    avg_price = 0
                    
                    # Portfolio 시트에서 해당 티커의 Avg_Price 찾기
                    for row in port_records:
                        row_ticker = str(row.get("Ticker", "")).replace("'", "").strip()
                        if row_ticker == ticker or row_ticker.zfill(6) == ticker:
                            avg_price = float(str(row.get("Avg_Price", "0")).replace(",", ""))
                            break
                            
                    if avg_price > 0:
                        realized_pnl = (price - avg_price) * shares
                        
                        try:
                            pnl_sheet = doc.worksheet("Realized_PnL")
                        except gspread.exceptions.WorksheetNotFound:
                            # 만약 migrate_db.py를 아직 안 돌렸다면 자동 생성
                            pnl_sheet = doc.add_worksheet(title="Realized_PnL", rows="1000", cols="10")
                            pnl_sheet.append_row(["Date", "Ticker", "Account", "Currency", "Sold_Shares", "Sell_Price", "Avg_Cost", "Realized_PnL"])
                        
                        # Realized_PnL 시트에 기록
                        pnl_sheet.append_row([today_date, ticker, account_type, currency, shares, price, avg_price, realized_pnl])
                        
                        profit_sign = "+" if realized_pnl > 0 else ""
                        reply_text += f"\n💰 **실현 손익 계산 완료:** {profit_sign}{realized_pnl:,.2f} {unit} (평단가: {avg_price:,.2f} {unit} 기준)"
                    else:
                        reply_text += "\n⚠️ 포트폴리오에서 해당 종목의 매수 평단가를 찾지 못해 실현 손익은 기록되지 않았습니다."
                        
                except Exception as ex:
                    print(f"PnL 처리 중 오류: {ex}")
            
            await update.message.reply_text(reply_text, parse_mode="Markdown")
            
        else:
            await update.message.reply_text("무슨 말씀인지 잘 모르겠어요. 다시 말씀해주세요!")
    except Exception as e:
        await update.message.reply_text(f"처리 중 오류가 발생했습니다: {e}")

@restricted
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
                currency = row.get("Currency", "USD" if str(ticker).isalpha() else "KRW")
                unit = "원" if currency == "KRW" else "$"
                try:
                    val = float(str(d_return).replace("%", "").strip())
                    icon = "🔴" if val > 0 else "🔵" if val < 0 else "⚪"
                except ValueError:
                    icon = "⚪"
                msg += f"▪️ **{ticker}** ({account_type} / {currency}) : {shares}주\n   (현재가: {c_price:,}{unit} / 1D: {icon} {d_return}%)\n\n"
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"포트폴리오 조회 중 오류가 발생했습니다: {e}")
