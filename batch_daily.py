import os
import sys
import datetime
import pandas as pd
import requests
import yfinance as yf
from dotenv import load_dotenv
from src.sheets_client import get_sheet_client
from src.ai_agent import analyze_portfolio

load_dotenv()
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

US_STOCK_NAME_REGISTRY = {
    '0013P0': 'RISE 미국은행TOP10', 
    'TSLA': '테슬라', 'AAPL': '애플', 'NVDA': '엔비디아', 'MSFT': '마이크로소프트',
    'GOOGL': '구글(알파벳 A)', 'GOOG': '구글(알파벳 C)', 'AMZN': '아마존', 'META': '메타',
    'NFLX': '넷플릭스', 'AMD': 'AMD', 'AVGO': '브로드컴', 'COST': '코스트코',
    'SMCI': '슈퍼마이크로컴퓨터', 'ASML': 'ASML', 'QCOM': '퀄컴', 'INTC': '인텔',
    'COIN': '코인베이스', 'NKE': '나이키', 'SBUX': '스타벅스', 'DIS': '디즈니',
    'PLTR': '팔란티어', 'ARM': 'ARM 홀딩스', 'MS': '모건스탠리', 'GS': '골드만삭스', 'JPM': 'JP모건',
    'SPY': 'SPY (S&P500)', 'VOO': 'VOO (S&P500)', 'IVV': 'IVV (S&P500)',
    'QQQ': 'QQQ (나스닥100)', 'TQQQ': 'TQQQ (나스닥 3배 레버리지)', 'SQQQ': 'SQQQ (나스닥 3배 인버스)',
    'SOXL': 'SOXL (반도체 3배 레버리지)', 'SOXS': 'SOXS (반도체 3배 인버스)',
    'SCHD': 'SCHD (미국 배당성장)', 'JEPI': 'JEPI (JP모건 커버드콜)', 
    'TLT': 'TLT (미 20년 국채)', 'TMF': 'TMF (미 국채 3배 레버리지)',
    'TSLL': 'TSLL (테슬라 2배 레버리지)', 'NVDL': 'NVDL (엔비디아 2배 레버리지)',
    'ARKX': 'ARKX (우주탐사 ETF)', 'XLY': 'XLY (소비재 ETF)', 'HON': '허니웰', 'IBM': 'IBM', 'ITB': 'ITB (미국주택 ETF)'
}

def get_usd_krw_rate():
    try:
        res = requests.get("https://open.er-api.com/v6/latest/USD", timeout=3)
        if res.status_code == 200: return float(res.json()["rates"]["KRW"])
    except: pass
    return 1350.0

def get_kst_now():
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)

def run_daily_batch(mode="all"):
    kst_now = get_kst_now()
    snapshot_time = "06:00:00" if kst_now.hour < 12 else "18:00:00"
    snapshot_date_str = f"{kst_now.strftime('%Y-%m-%d')} {snapshot_time}"
    
    print(f"🚀 일일 배치 작업 시작 (실행 모드: {mode}, 스냅샷 기준: {snapshot_date_str})")

    client = get_sheet_client()
    doc = client.open_by_key(SPREADSHEET_ID)
    usd_krw = get_usd_krw_rate()

    tx_records = doc.worksheet("Transaction").get_all_records()
    holdings = {}
    for row in tx_records:
        row_clean = {str(k).strip().lower(): v for k, v in row.items()}
        ticker = str(row_clean.get('ticker', '')).strip()
        action = str(row_clean.get('type', '')).strip()
        if not ticker: continue
        if ticker.isdigit(): ticker = ticker.zfill(6)
        
        shares = float(str(row_clean.get('shares', '0')).replace(',', ''))
        price = float(str(row_clean.get('price', '0')).replace(',', ''))
        currency = str(row_clean.get('currency', 'KRW')).strip().upper()
        account = str(row_clean.get('account', '일반')).strip()
        
        key = (ticker, account, currency)
        if key not in holdings:
            holdings[key] = {'shares': 0.0, 'total_cost': 0.0}
        
        if action in ['매수', 'buy', '입고']:
            holdings[key]['shares'] += shares
            holdings[key]['total_cost'] += (shares * price)
        elif action in ['매도', 'sell', '출고']:
            if holdings[key]['shares'] > 0:
                avg_p = holdings[key]['total_cost'] / holdings[key]['shares']
                holdings[key]['shares'] -= shares
                holdings[key]['total_cost'] = holdings[key]['shares'] * avg_p
            else:
                holdings[key]['shares'] -= shares

    port_sheet = doc.worksheet("Portfolio")
    old_prices = {}
    for r in port_sheet.get_all_records():
        t = str(r.get("Ticker", "")).strip()
        if t.isdigit(): t = t.zfill(6)
        old_prices[t] = (r.get("Current_Price", 0), r.get("1D_Return", "0.00%"), str(r.get("Stock_Name", t)))

    portfolio_rows = []
    history_rows = []
    portfolio_text_list = [] 

    for key, data in holdings.items():
        ticker, account, currency = key
        shares = data['shares']
        if shares <= 0: continue

        avg_price = data['total_cost'] / shares
        
        # [수정 1] 영문이 섞인 한국 ETF(0013P0)도 완벽하게 한국 주식으로 분류
        is_kr = ticker.isdigit() or currency == 'KRW' or any(c.isdigit() for c in ticker) and len(ticker) == 6
        
        current_price = avg_price
        one_day_return = "0.00%"
        
        if ticker in old_prices:
            current_price, one_day_return, stock_name = old_prices[ticker]
        else:
            stock_name = ticker if is_kr else US_STOCK_NAME_REGISTRY.get(ticker.upper(), ticker.upper())

        should_fetch = True
        if mode == "kr" and not is_kr: should_fetch = False
        if mode == "us" and is_kr: should_fetch = False

        if should_fetch:
            print(f"[{ticker}] 최신 시세 동기화 중...")
            try:
                if is_kr:
                    # [수정 2] 네이버 금융 모바일 API 직결 통신 (모든 ETF 및 394800 같은 신규 종목 100% 지원)
                    url = f"https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{ticker}"
                    res = requests.get(url, timeout=5).json()
                    item = res['result']['areas'][0]['datas'][0]
                    current_price = float(item['nv'])
                    raw_return = float(item['cr'])
                    one_day_return = f"{raw_return:+.2f}%"
                    stock_name = item['nm'] # 네이버에서 정확한 공식 한글 종목명도 알아서 가져옴
                else: 
                    # 미국 주식은 기존 야후 파이낸스 유지
                    df_stock = yf.Ticker(ticker).history(period="7d")
                    if not df_stock.empty:
                        df_stock = df_stock.dropna(subset=['Close'])
                        if len(df_stock) >= 1:
                            current_price = float(df_stock['Close'].iloc[-1])
                            if len(df_stock) >= 2:
                                prev_close = float(df_stock['Close'].iloc[-2])
                                raw_return = ((current_price - prev_close) / prev_close) * 100
                                one_day_return = f"{raw_return:+.2f}%"
            except Exception as e:
                print(f"⚠️ [{ticker}] 시세 연동 실패: {e}")

        total_value_krw = shares * current_price * usd_krw if currency == 'USD' else shares * current_price
        safe_ticker = f"'{ticker}" if is_kr else ticker
        
        portfolio_rows.append([safe_ticker, stock_name, shares, round(avg_price, 2), current_price, one_day_return, currency, account])
        history_rows.append([snapshot_date_str, safe_ticker, stock_name, total_value_krw, account])
        portfolio_text_list.append(f"Ticker: {ticker} | Name: {stock_name} | Shares: {shares} | Avg_Price: {avg_price:.2f} | Current_Price: {current_price:.2f} | 1D_Return: {one_day_return}")

    port_sheet.clear()
    port_headers = ["Ticker", "Stock_Name", "Shares", "Avg_Price", "Current_Price", "1D_Return", "Currency", "Account"]
    port_sheet.append_row(port_headers)
    if portfolio_rows: port_sheet.append_rows(portfolio_rows)

    try: hist_sheet = doc.worksheet("History")
    except: hist_sheet = doc.add_worksheet(title="History", rows="1000", cols="10")
        
    hist_header = ["Date", "Ticker", "Stock_Name", "Total_Value_KRW", "Account"]
    all_hist_values = hist_sheet.get_all_values()
    if not all_hist_values or all_hist_values[0][0] != "Date": hist_sheet.insert_row(hist_header, index=1)
        
    all_hist_records = hist_sheet.get_all_records()
    if all_hist_records:
        df_hist_temp = pd.DataFrame(all_hist_records)
        for col in hist_header:
            if col not in df_hist_temp.columns: df_hist_temp[col] = ""
        df_hist_temp = df_hist_temp[hist_header]
        
        if 'Date' in df_hist_temp.columns:
            df_keep = df_hist_temp[df_hist_temp['Date'].astype(str).str.strip() != snapshot_date_str]
            hist_sheet.clear()
            hist_sheet.append_row(hist_header)
            if not df_keep.empty: hist_sheet.append_rows(df_keep.values.tolist())
    else:
        hist_sheet.clear()
        hist_sheet.append_row(hist_header)

    if history_rows: hist_sheet.append_rows(history_rows)
    print("✅ 포트폴리오 및 히스토리 스냅샷 저장 완료!")

    if mode in ["us", "all"]:
        portfolio_data_str = "\n".join(portfolio_text_list)
        if portfolio_data_str.strip():
            print("🚀 [AI 분석] 4인 4색 페르소나 리포트 생성 중...")
            personas = ["quant", "macro", "value", "ten_bagger"]
            ai_results = {}
            for p in personas:
                print(f"🤖 [{p.upper()}] 분석 중...")
                ai_results[p] = analyze_portfolio(portfolio_data_str, p)
            
            ai_reports_sheet = doc.worksheet("AI_Reports")
            ai_reports_sheet.append_row([snapshot_date_str, ai_results["quant"], ai_results["macro"], ai_results["value"], ai_results["ten_bagger"]])
            print("🎉 AI 분석 리포트 저장 완료!")

if __name__ == "__main__":
    run_mode = "all"
    if len(sys.argv) > 1: run_mode = sys.argv[1].lower()
    run_daily_batch(run_mode)
