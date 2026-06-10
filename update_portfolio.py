import os
import datetime
import json
import pandas as pd
import requests
import math
import pickle
import time
import FinanceDataReader as fdr
from dotenv import load_dotenv
from src.sheets_client import get_sheet_client

# 환경변수 로드
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
    'TSLL': 'TSLL (테슬라 2배 레버리지)', 'NVDL': 'NVDL (엔비디아 2배 레버리지)'
}

def get_val(d, keys, default=''):
    for k in keys:
        if k in d and d[k] != '':
            return d[k]
    return default

def get_usd_krw_rate():
    try:
        res = requests.get("https://open.er-api.com/v6/latest/USD", timeout=3)
        if res.status_code == 200:
            return float(res.json()["rates"]["KRW"])
    except Exception:
        pass
    return 1350.0

def get_kst_now():
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    return utc_now + datetime.timedelta(hours=9)

def clean_float(val):
    if math.isnan(val) or math.isinf(val):
        return 0.0
    return val

def get_cached_registry():
    """KRX/ETF 종목 레지스트리를 캐싱하여 로딩 속도 10배 향상"""
    cache_file = "krx_etf_cache.pkl"
    cache_expiry = 259200 # 3일

    if os.path.exists(cache_file) and time.time() - os.path.getmtime(cache_file) < cache_expiry:
        print("📦 로컬 캐시에서 마스터 레지스트리를 불러옵니다 (속도 최적화 적용).")
        with open(cache_file, 'rb') as f:
            return pickle.load(f)

    print("🌐 마스터 레지스트리 새로 다운로드 중...")
    krx_name_registry = {}
    try:
        df_krx = fdr.StockListing('KRX')
        krx_name_registry.update(dict(zip(df_krx['Code'].astype(str), df_krx['Name'].astype(str))))
        
        df_etf = fdr.StockListing('ETF/KR')
        code_col = 'Symbol' if 'Symbol' in df_etf.columns else 'Code' if 'Code' in df_etf.columns else df_etf.columns[0]
        name_col = 'Name' if 'Name' in df_etf.columns else df_etf.columns[1]
        
        etf_registry = dict(zip(df_etf[code_col].astype(str), df_etf[name_col].astype(str)))
        krx_name_registry.update(etf_registry)
        
        with open(cache_file, 'wb') as f:
            pickle.dump(krx_name_registry, f)
    except Exception as e:
        print(f"⚠️ 레지스트리 로드 실패: {e}")
        
    return krx_name_registry

def run_portfolio_settlement():
    kst_now = get_kst_now()
    print(f"[{kst_now}] 🔄 대한민국 표준시(KST) 기준 자산 정산 엔진 구동...")
    
    try:
        sheet_client = get_sheet_client()
        doc = sheet_client.open_by_key(SPREADSHEET_ID)
        usd_krw = get_usd_krw_rate()
        
        tx_sheet = doc.worksheet("Transaction")
        tx_records = tx_sheet.get_all_records()
        
        if not tx_records:
            print("⚠️ 거래 기록이 비어있어 정산을 종료합니다.")
            return
            
        krx_name_registry = get_cached_registry()
        
        holdings = {}
        for row in tx_records:
            row_clean = {str(k).strip().lower(): v for k, v in row.items()}
            ticker = str(get_val(row_clean, ['ticker', '종목', '종목코드', '티커'], '')).strip()
            action = str(get_val(row_clean, ['action', 'type', '구분', '매매', '액션', '종류'], '')).strip()
            
            if not ticker or ticker.lower() == 'none':
                continue
            if ticker.isdigit():
                ticker = ticker.zfill(6)
                
            try:
                shares_raw = str(get_val(row_clean, ['shares', '수량', '수량(주)', '주식수', '보유수량'], '0')).replace(',', '').strip()
                shares = float(shares_raw) if shares_raw else 0.0
            except ValueError: shares = 0.0
                
            try:
                price_raw = str(get_val(row_clean, ['price', '단가', '매입단가', '평단가', '가격', '구매단가'], '0')).replace(',', '').strip()
                price = float(price_raw) if price_raw else 0.0
            except ValueError: price = 0.0
                
            currency = str(get_val(row_clean, ['currency', '통화', '거래통화'], '')).strip()
            account = str(get_val(row_clean, ['account', '계좌', '계좌구분'], '일반')).strip()
            
            if account in ['KRW', 'USD'] or currency in ['일반', '연금']:
                account, currency = currency, account
            if not currency:
                currency = 'USD' if ticker.isalpha() else 'KRW'
                
            key = (ticker, account, currency)
            if key not in holdings:
                holdings[key] = {'shares': 0.0, 'total_cost': 0.0}
            
            if action in ['매수', 'buy', 'Buy', 'BUY', '지급', '입고']:
                holdings[key]['shares'] += shares
                holdings[key]['total_cost'] += (shares * price)
            elif action in ['매도', 'sell', 'Sell', 'SELL', '출고']:
                if holdings[key]['shares'] > 0:
                    avg_p = holdings[key]['total_cost'] / holdings[key]['shares']
                    holdings[key]['shares'] -= shares
                    holdings[key]['total_cost'] = holdings[key]['shares'] * avg_p
                else:
                    holdings[key]['shares'] -= shares

        portfolio_rows = []
        history_rows = []
        
        today_str = kst_now.strftime('%Y-%m-%d')
        start_str = (kst_now - datetime.timedelta(days=15)).strftime('%Y-%m-%d')

        for key, data in holdings.items():
            ticker, account, currency = key
            shares = data['shares']
            
            if shares <= 0:
                continue
                
            avg_price = data['total_cost'] / shares if shares > 0 else 0
            current_price = avg_price
            one_day_return = "0.00%"
            
            if ticker.isdigit():
                stock_name = krx_name_registry.get(ticker, f"국내증권({ticker})")
            else:
                stock_name = US_STOCK_NAME_REGISTRY.get(ticker.upper(), ticker.upper())
            
            try:
                df_stock = fdr.DataReader(ticker, start=start_str)
                if df_stock is not None and not df_stock.empty:
                    df_stock = df_stock.dropna(subset=['Close'])
                    if len(df_stock) >= 1:
                        current_price = float(df_stock.iloc[-1]['Close'])
                        if len(df_stock) >= 2:
                            prev_close = float(df_stock.iloc[-2]['Close'])
                            raw_return = ((current_price - prev_close) / prev_close) * 100
                            one_day_return = f"{raw_return:+.2f}%"
            except Exception as e:
                print(f"⚠️ [{ticker}] 실시간 시세 연동 실패: {e}")

            total_value_krw = shares * current_price * usd_krw if currency == 'USD' else shares * current_price

            avg_price = clean_float(avg_price)
            current_price = clean_float(current_price)
            total_value_krw = clean_float(total_value_krw)

            portfolio_rows.append([ticker, stock_name, int(shares) if shares.is_integer() else shares, round(avg_price, 2), current_price, one_day_return, currency, account])
            history_rows.append([today_str, ticker, stock_name, total_value_krw, account])

        port_sheet = doc.worksheet("Portfolio")
        port_sheet.clear()
        port_headers = ["Ticker", "Stock_Name", "Shares", "Avg_Price", "Current_Price", "1D_Return", "Currency", "Account"]
        port_sheet.append_row(port_headers)
        if portfolio_rows:
            port_sheet.append_rows(portfolio_rows)
            
        try:
            hist_sheet = doc.worksheet("History")
        except Exception:
            hist_sheet = doc.add_worksheet(title="History", rows="1000", cols="10")
            
        hist_header = ["Date", "Ticker", "Stock_Name", "Total_Value_KRW", "Account"]
        all_hist_values = hist_sheet.get_all_values()
        
        if not all_hist_values or all_hist_values[0][0] != "Date":
            hist_sheet.insert_row(hist_header, index=1)
            
        all_hist_records = hist_sheet.get_all_records()
        
        if all_hist_records:
            df_hist_temp = pd.DataFrame(all_hist_records)
            if 'Date' in df_hist_temp.columns:
                df_keep = df_hist_temp[df_hist_temp['Date'].astype(str).str.strip() != today_str]
                hist_sheet.clear()
                hist_sheet.append_row(hist_header)
                if not df_keep.empty:
                    hist_sheet.append_rows(df_keep.values.tolist())
        else:
            hist_sheet.clear()
            hist_sheet.append_row(hist_header)

        if history_rows:
            hist_sheet.append_rows(history_rows)

        print(f"✅ [자산 정산 및 시세 복원 완료] {today_str} 일자 정산 및 갱신 성공!")

    except Exception as e:
        print(f"❌ 정산 엔진 가동 중 시스템 예외 발생: {e}")

if __name__ == "__main__":
    run_portfolio_settlement()
