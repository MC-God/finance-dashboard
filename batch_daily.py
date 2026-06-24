import os
import sys
import datetime
import pandas as pd
import requests
import yfinance as yf
import FinanceDataReader as fdr
from dotenv import load_dotenv
from src.sheets_client import get_sheet_client
from src.ai_agent import analyze_portfolio
import time

load_dotenv()
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_USER_IDS = [int(uid.strip()) for uid in os.getenv("ALLOWED_USER_IDS", "").split(",") if uid.strip()]

US_STOCK_NAME_REGISTRY = {
    '0013P0': 'RISE 미국은행TOP10', 'TSLA': '테슬라', 'AAPL': '애플', 'NVDA': '엔비디아', 'MSFT': '마이크로소프트',
    'GOOGL': '구글(알파벳 A)', 'GOOG': '구글(알파벳 C)', 'AMZN': '아마존', 'META': '메타', 'NFLX': '넷플릭스', 
    'AMD': 'AMD', 'AVGO': '브로드컴', 'COST': '코스트코', 'SMCI': '슈퍼마이크로컴퓨터', 'ASML': 'ASML', 
    'QCOM': '퀄컴', 'INTC': '인텔', 'COIN': '코인베이스', 'NKE': '나이키', 'SBUX': '스타벅스', 'DIS': '디즈니',
    'PLTR': '팔란티어', 'ARM': 'ARM 홀딩스', 'MS': '모건스탠리', 'GS': '골드만삭스', 'JPM': 'JP모건',
    'SPY': 'SPY (S&P500)', 'VOO': 'VOO (S&P500)', 'IVV': 'IVV (S&P500)', 'QQQ': 'QQQ (나스닥100)', 
    'TQQQ': 'TQQQ (나스닥 3배)', 'SQQQ': 'SQQQ (인버스 3배)', 'SOXL': 'SOXL (반도체 3배)', 'SOXS': 'SOXS (인버스 3배)',
    'SCHD': 'SCHD (배당)', 'JEPI': 'JEPI (배당)', 'TLT': 'TLT (20년 국채)', 'TMF': 'TMF (국채 3배)',
    'TSLL': 'TSLL (테슬라 2배)', 'NVDL': 'NVDL (엔비디아 2배)'
}

def get_usd_krw_rate():
    try:
        res = requests.get("https://open.er-api.com/v6/latest/USD", timeout=3)
        if res.status_code == 200: return float(res.json()["rates"]["KRW"])
    except: pass
    return 1350.0

def get_kst_now():
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)

def send_telegram_push(message: str):
    if not TELEGRAM_TOKEN or not ALLOWED_USER_IDS: return
    for user_id in ALLOWED_USER_IDS:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        try: requests.post(url, json={"chat_id": user_id, "text": message}, timeout=5)
        except: pass

def run_daily_batch(mode="all"):
    kst_now = get_kst_now()
    snapshot_time = "06:00:00" if kst_now.hour < 12 else "18:00:00"
    snapshot_date_str = f"{kst_now.strftime('%Y-%m-%d')} {snapshot_time}"
    
    print(f"🚀 일일 배치 작업 시작 (실행 모드: {mode}, 스냅샷 기준: {snapshot_date_str})")

    client = get_sheet_client()
    doc = client.open_by_key(SPREADSHEET_ID)
    usd_krw = get_usd_krw_rate()

    krx_name_registry = {}
    try:
        df_krx = fdr.StockListing('KRX')
        krx_name_registry.update(dict(zip(df_krx['Code'].astype(str), df_krx['Name'].astype(str))))
    except: pass

    tx_records = doc.worksheet("Transaction").get_all_records()
    holdings = {}
    for row in tx_records:
        row_clean = {str(k).strip().lower(): v for k, v in row.items()}
        ticker, action = str(row_clean.get('ticker', '')).replace("'", "").strip(), str(row_clean.get('type', '')).strip()
        if not ticker: continue
        if ticker.isdigit(): ticker = ticker.zfill(6)
        
        shares = float(str(row_clean.get('shares', '0')).replace(',', ''))
        price = float(str(row_clean.get('price', '0')).replace(',', ''))
        currency = str(row_clean.get('currency', 'KRW')).strip().upper()
        account = str(row_clean.get('account', '일반')).strip()
        
        key = (ticker, account, currency)
        if key not in holdings: holdings[key] = {'shares': 0.0, 'total_cost': 0.0}
        
        if action in ['매수', 'buy', '입고']:
            holdings[key]['shares'] += shares
            holdings[key]['total_cost'] += (shares * price)
        elif action in ['매도', 'sell', '출고']:
            if holdings[key]['shares'] > 0:
                avg_p = holdings[key]['total_cost'] / holdings[key]['shares']
                holdings[key]['shares'] -= shares
                holdings[key]['total_cost'] = holdings[key]['shares'] * avg_p
            else: holdings[key]['shares'] -= shares

    port_sheet = doc.worksheet("Portfolio")
    old_prices = {}
    for r in port_sheet.get_all_records():
        t = str(r.get("Ticker", "")).replace("'", "").strip()
        if t.isdigit(): t = t.zfill(6)
        # 구글 시트에서 가져온 가격에 콤마나 텍스트가 섞여있어도 안전하게 숫자로 변환하는 방어 로직
        raw_price = str(r.get("Current_Price", "0")).replace(',', '').replace('$', '').replace('원', '').strip()
        try: c_price = float(raw_price)
        except: c_price = 0.0
        old_prices[t] = (c_price, str(r.get("1D_Return", "0.00%")), str(r.get("Stock_Name", t)))

    portfolio_rows, history_rows, portfolio_text_list = [], [], []

    for key, data in holdings.items():
        ticker, account, currency = key
        shares = data['shares']
        if shares <= 0: continue
        avg_price = data['total_cost'] / shares
        is_kr = ticker.isdigit() or currency == 'KRW' or (any(c.isdigit() for c in ticker) and len(ticker) == 6)
        
        # 1. 기본값 세팅 (포트폴리오에 처음 들어온 신규 종목일 경우 매수가를 임시 현재가로 사용)
        current_price = avg_price
        one_day_return = "0.00%"
        stock_name = krx_name_registry.get(ticker, ticker) if is_kr else US_STOCK_NAME_REGISTRY.get(ticker.upper(), ticker.upper())

        # 2. [핵심 버그 수정] 기존 포트폴리오에 있던 종목이면, 무조건 어제 종가(기존 현재가)를 먼저 계승!
        if ticker in old_prices:
            current_price = old_prices[ticker][0]
            one_day_return = old_prices[ticker][1]
            stock_name = old_prices[ticker][2]

        # 3. 해당 장(Market) 배치일 때만 API를 찔러서 최신화 (한국장 배치일 땐 한국 종목만, 미국장일 땐 미국 종목만 덮어씀)
        if (mode == "kr" and is_kr) or (mode == "us" and not is_kr) or mode == "all":
            print(f"[{ticker}] 최신 시세 동기화 중...")
            try:
                if is_kr:
                    res = requests.get(f"https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{ticker}", timeout=5).json()
                    item = res['result']['areas'][0]['datas'][0]
                    current_price = float(item['nv'])
                    one_day_return = f"{float(item['cr']):+.2f}%"
                else: 
                    df_stock = yf.Ticker(ticker).history(period="7d").dropna(subset=['Close'])
                    if not df_stock.empty:
                        current_price = float(df_stock['Close'].iloc[-1])
                        if len(df_stock) >= 2: 
                            prev_close = float(df_stock['Close'].iloc[-2])
                            one_day_return = f"{((current_price - prev_close) / prev_close * 100):+.2f}%"
            except Exception as e:
                print(f"⚠️ [{ticker}] 시세 연동 실패: {e}")

        total_value_krw = shares * current_price * (usd_krw if currency == 'USD' else 1)
        safe_ticker = f"'{ticker}" if is_kr else ticker
        
        portfolio_rows.append([safe_ticker, stock_name, shares, round(avg_price, 2), current_price, one_day_return, currency, account])
        history_rows.append([snapshot_date_str, safe_ticker, stock_name, total_value_krw, account])
        portfolio_text_list.append(f"Ticker: {ticker} | Shares: {shares} | Avg_Price: {avg_price:.2f} | Current_Price: {current_price:.2f} | 1D: {one_day_return}")

    port_sheet.clear(); port_sheet.append_row(["Ticker", "Stock_Name", "Shares", "Avg_Price", "Current_Price", "1D_Return", "Currency", "Account"])
    if portfolio_rows: port_sheet.append_rows(portfolio_rows)

    try: hist_sheet = doc.worksheet("History")
    except: hist_sheet = doc.add_worksheet(title="History", rows="1000", cols="10")
    
    if not hist_sheet.get_all_values(): hist_sheet.append_row(["Date", "Ticker", "Stock_Name", "Total_Value_KRW", "Account"])
    if history_rows: hist_sheet.append_rows(history_rows)

    # 4. AI 리포트는 하루의 모든 장이 끝나는 시점(미국장 마감 = "us" 모드)에 한 번만 실행됨
    if mode in ["us", "all"]:
        portfolio_data_str = "\n".join(portfolio_text_list)
        if portfolio_data_str.strip():
            print("🚀 [AI 분석] 리포트 생성 및 텔레그램 푸시 중...")
            ai_results = {}
            send_telegram_push(f"🔔 **오늘의 포트폴리오 AI 분석 완료! ({snapshot_date_str})**\n\n4인 4색 전문가 리포트를 차례로 전송합니다.")
            
            for p, name in [("quant", "📉 퀀트"), ("macro", "🌍 매크로"), ("value", "💎 가치투자"), ("ten_bagger", "🚀 텐베거")]:
                ai_results[p] = analyze_portfolio(portfolio_data_str, p)
                send_telegram_push(f"**[{name} 의견]**\n\n{ai_results[p]}")
                time.sleep(1)
            
            doc.worksheet("AI_Reports").append_row([snapshot_date_str, ai_results["quant"], ai_results["macro"], ai_results["value"], ai_results["ten_bagger"]])
            print("🎉 AI 분석 리포트 저장 완료!")

if __name__ == "__main__":
    run_mode = "all"
    if len(sys.argv) > 1: run_mode = sys.argv[1].lower()
    run_daily_batch(run_mode)
