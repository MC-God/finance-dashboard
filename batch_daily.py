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

load_dotenv()
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

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
    # 1. 하루 2번 스냅샷을 위해 시간대(오전 6시 / 오후 6시) 지정
    snapshot_time = "06:00:00" if kst_now.hour < 12 else "18:00:00"
    snapshot_date_str = f"{kst_now.strftime('%Y-%m-%d')} {snapshot_time}"
    
    print(f"🚀 일일 배치 작업 시작 (실행 모드: {mode}, 스냅샷 기준: {snapshot_date_str})")

    client = get_sheet_client()
    doc = client.open_by_key(SPREADSHEET_ID)
    usd_krw = get_usd_krw_rate()

    # 2. Transaction 기반 보유 주식 정밀 계산
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

    # 3. 기존 Portfolio 데이터 (업데이트 건너뛸 종목의 가격 유지용)
    port_sheet = doc.worksheet("Portfolio")
    old_prices = {str(r.get("Ticker")).strip(): (r.get("Current_Price", 0), r.get("1D_Return", "0.00%"), str(r.get("Stock_Name", ticker))) for r in port_sheet.get_all_records()}

    portfolio_rows = []
    history_rows = []
    portfolio_text_list = [] 

    # 4. 시세 업데이트 연산
    for key, data in holdings.items():
        ticker, account, currency = key
        shares = data['shares']
        if shares <= 0: continue

        avg_price = data['total_cost'] / shares
        is_kr = ticker.isdigit()
        
        current_price = avg_price
        one_day_return = "0.00%"
        stock_name = ticker

        if ticker in old_prices:
            current_price, one_day_return, stock_name = old_prices[ticker]

        # 모드별 타겟팅 (kr이면 미국주식 패스, us면 한국주식 패스)
        should_fetch = True
        if mode == "kr" and not is_kr: should_fetch = False
        if mode == "us" and is_kr: should_fetch = False

        if should_fetch:
            print(f"[{ticker}] 최신 시세 동기화 중...")
            try:
                if is_kr:
                    df_stock = fdr.DataReader(ticker, start=(kst_now - datetime.timedelta(days=7)).strftime('%Y-%m-%d'))
                else:
                    df_stock = yf.Ticker(ticker).history(period="7d")
                    
                if df_stock is not None and not df_stock.empty:
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

        portfolio_rows.append([ticker, stock_name, shares, round(avg_price, 2), current_price, one_day_return, currency, account])
        history_rows.append([snapshot_date_str, ticker, stock_name, total_value_krw, account])
        portfolio_text_list.append(f"Ticker: {ticker} | Shares: {shares} | Avg_Price: {avg_price:.2f} | Current_Price: {current_price:.2f} | 1D_Return: {one_day_return}")

    # 5. Portfolio 시트 덮어쓰기
    port_sheet.clear()
    port_headers = ["Ticker", "Stock_Name", "Shares", "Avg_Price", "Current_Price", "1D_Return", "Currency", "Account"]
    port_sheet.append_row(port_headers)
    if portfolio_rows: port_sheet.append_rows(portfolio_rows)

    # 6. History 스냅샷 저장 (중복 시간대 안전 제거 후 추가)
    try: hist_sheet = doc.worksheet("History")
    except: hist_sheet = doc.add_worksheet(title="History", rows="1000", cols="10")
        
    hist_header = ["Date", "Ticker", "Stock_Name", "Total_Value_KRW", "Account"]
    all_hist_values = hist_sheet.get_all_values()
    if not all_hist_values or all_hist_values[0][0] != "Date": hist_sheet.insert_row(hist_header, index=1)
        
    all_hist_records = hist_sheet.get_all_records()
    if all_hist_records:
        df_hist_temp = pd.DataFrame(all_hist_records)
        if 'Date' in df_hist_temp.columns:
            df_keep = df_hist_temp[df_hist_temp['Date'].astype(str).str.strip() != snapshot_date_str]
            hist_sheet.clear()
            hist_sheet.append_row(hist_header)
            if not df_keep.empty: hist_sheet.append_rows(df_keep.values.tolist())
    else:
        hist_sheet.clear()
        hist_sheet.append_row(hist_header)

    if history_rows: hist_sheet.append_rows(history_rows)
    print("✅ 포트폴리오 및 히스토리 스냅샷 (오전/오후) 저장 완료!")

    # 7. AI 분석 로직 (미국장 마감 시, 또는 수동 all 모드일 때만 실행)
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
