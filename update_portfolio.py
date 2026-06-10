import os
import datetime
import pandas as pd
import requests
import FinanceDataReader as fdr
from dotenv import load_dotenv
from src.sheets_client import get_sheet_client

# 환경변수 로드
load_dotenv()
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

# 🇺🇸 미국 주식 및 대표 ETF 고정 표준 매핑 소스 (특수 코드 포함)
US_STOCK_NAME_REGISTRY = {
    # 💡 확실한 원천 소스 고정 매핑
    '0013P0': 'RISE 미국은행TOP10', 

    # 주요 메가캡 기술주
    'TSLA': '테슬라', 'AAPL': '애플', 'NVDA': '엔비디아', 'MSFT': '마이크로소프트',
    'GOOGL': '구글(알파벳 A)', 'GOOG': '구글(알파벳 C)', 'AMZN': '아마존', 'META': '메타',
    'NFLX': '넷플릭스', 'AMD': 'AMD', 'AVGO': '브로드컴', 'COST': '코스트코',
    'SMCI': '슈퍼마이크로컴퓨터', 'ASML': 'ASML', 'QCOM': '퀄컴', 'INTC': '인텔',
    'COIN': '코인베이스', 'NKE': '나이키', 'SBUX': '스타벅스', 'DIS': '디즈니',
    'PLTR': '팔란티어', 'ARM': 'ARM 홀딩스', 'MS': '모건스탠리', 'GS': '골드만삭스', 'JPM': 'JP모건',
    
    # 지수 및 레버리지 / 인버스 주요 미국 ETF
    'SPY': 'SPY (S&P500)', 'VOO': 'VOO (S&P500)', 'IVV': 'IVV (S&P500)',
    'QQQ': 'QQQ (나스닥100)', 'TQQQ': 'TQQQ (나스닥 3배 레버리지)', 'SQQQ': 'SQQQ (나스닥 3배 인버스)',
    'SOXL': 'SOXL (반도체 3배 레버리지)', 'SOXS': 'SOXS (반도체 3배 인버스)',
    
    # 배당 및 채권형 미국 ETF
    'SCHD': 'SCHD (미국 배당성장)', 'JEPI': 'JEPI (JP모건 커버드콜)', 
    'TLT': 'TLT (미 20년 국채)', 'TMF': 'TMF (미 국채 3배 레버리지)',
    
    # 개별 종목 레버리지 미국 ETF
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

def run_portfolio_settlement():
    print(f"[{datetime.datetime.now()}] 🔄 [인프라 확정] 주식+ETF 마스터 소스 자산 정산 엔진 가동...")
    
    try:
        sheet_client = get_sheet_client()
        doc = sheet_client.open_by_key(SPREADSHEET_ID)
        usd_krw = get_usd_krw_rate()
        
        tx_sheet = doc.worksheet("Transaction")
        tx_records = tx_sheet.get_all_records()
        
        if not tx_records:
            print("⚠️ 거래 기록이 비어있어 정산을 종료합니다.")
            return
            
        krx_name_registry = {}
        
        # 2-1. 일반 상장 주식 동기화
        print("📋 한국거래소(KRX) 상장 주식 마스터 레지스트리 동기화 중...")
        try:
            df_krx = fdr.StockListing('KRX')
            krx_name_registry.update(dict(zip(df_krx['Code'].astype(str), df_krx['Name'].astype(str))))
            print(f"   - 일반 주식 장부 확보 완료 (누적 {len(krx_name_registry)}개)")
        except Exception as e:
            print(f"⚠️ KRX 주식 레지스트리 로드 실패: {e}")
            
        # 2-2. 국내 상장 ETF 전체 마스터 데이터 병합
        print("📋 대한민국 상장 ETF 마스터 레지스트리 추가 연동 및 병합 중...")
        try:
            df_etf = fdr.StockListing('ETF/KR')
            code_col = 'Symbol' if 'Symbol' in df_etf.columns else 'Code' if 'Code' in df_etf.columns else df_etf.columns[0]
            name_col = 'Name' if 'Name' in df_etf.columns else df_etf.columns[1]
            
            etf_registry = dict(zip(df_etf[code_col].astype(str), df_etf[name_col].astype(str)))
            krx_name_registry.update(etf_registry)
            print(f"✅ 국내 일반 주식 및 ETF 통합 마스터 구축 완료 (최종 {len(krx_name_registry)}개 종목 매핑 소스 대기)")
        except Exception as e:
            print(f"⚠️ 국내 ETF 레지스트리 로드 실패: {e}")
        
        # 3. 잔고 및 보유 종목 연산
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
            except ValueError:
                shares = 0.0
                
            try:
                price_raw = str(get_val(row_clean, ['price', '단가', '매입단가', '평단가', '가격', '구매단가'], '0')).replace(',', '').strip()
                price = float(price_raw) if price_raw else 0.0
            except ValueError:
                price = 0.0
                
            currency = str(get_val(row_clean, ['currency', '통화', '거래통화'], '')).strip()
            account = str(get_val(row_clean, ['account', '계좌', '계좌구분'], '일반')).strip()
            
            # 배선 오류 과거 정산 보정 로직
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

        # 4. 각 종목별 시세 매칭 및 확정 소스 매핑
        portfolio_rows = []
        history_rows = []
        today_str = datetime.date.today().strftime('%Y-%m-%d')
        start_str = (datetime.date.today() - datetime.timedelta(days=15)).strftime('%Y-%m-%d')

        for key, data in holdings.items():
            ticker, account, currency = key
            shares = data['shares']
            
            if shares <= 0:
                continue
                
            avg_price = data['total_cost'] / shares if shares > 0 else 0
            current_price = avg_price
            one_day_return = "0.00%"
            
            # 결정론적 1:1 리얼타임 명칭 매핑
            if ticker.isdigit():
                stock_name = krx_name_registry.get(ticker, f"국내증권({ticker})")
            else:
                stock_name = US_STOCK_NAME_REGISTRY.get(ticker.upper(), ticker.upper())
            
            try:
                # 💡 [정밀 교정] 0013P0 시세 연동 로직 정상화
                # 0013P0 규격 그대로 파이낸스 데이터레이더에 입력하여 본래 가격을 동기화합니다.
                df_stock = fdr.DataReader(ticker, start=start_str)
                
                # 만약 특수 문자로 인해 기본 조회가 실패할 경우를 대비한 KRX 국내 ETF 표준 코드(480430) 하이브리드 교차 조회 안전망
                if (df_stock is None or df_stock.empty) and ticker == '0013P0':
                    df_stock = fdr.DataReader('480430', start=start_str)
                    
                if df_stock is not None and not df_stock.empty and len(df_stock) >= 1:
                    current_price = float(df_stock.iloc[-1]['Close'])
                    if len(df_stock) >= 2:
                        prev_close = float(df_stock.iloc[-2]['Close'])
                        raw_return = ((current_price - prev_close) / prev_close) * 100
                        one_day_return = f"{raw_return:+.2f}%"
            except Exception as e:
                print(f"⚠️ [{ticker}] 실시간 시세 연동 실패 (기본 단가 보존): {e}")

            total_value_krw = shares * current_price * usd_krw if currency == 'USD' else shares * current_price

            # 💡 중요: 최종 장부 아웃풋 데이터에도 원본 키인 'ticker'("0013P0")를 완벽 보존하여 내보냅니다.
            portfolio_rows.append([
                ticker,
                stock_name,
                int(shares) if shares.is_integer() else shares,
                round(avg_price, 2),
                current_price,
                one_day_return,
                currency,
                account
            ])
            
            history_rows.append([
                today_str,
                ticker,
                stock_name,
                total_value_krw,
                account
            ])

        # Portfolio 시트 Overwrite
        port_sheet = doc.worksheet("Portfolio")
        port_sheet.clear()
        port_headers = ["Ticker", "Stock_Name", "Shares", "Avg_Price", "Current_Price", "1D_Return", "Currency", "Account"]
        port_sheet.append_row(port_headers)
        if portfolio_rows:
            port_sheet.append_rows(portfolio_rows)
            
        # History 시트 적재
        try:
            hist_sheet = doc.worksheet("History")
        except Exception:
            hist_sheet = doc.add_worksheet(title="History", rows="1000", cols="10")
            hist_sheet.append_row(["Date", "Ticker", "Stock_Name", "Total_Value_KRW", "Account"])
            
        all_hist_records = hist_sheet.get_all_records()
        if all_hist_records:
            df_hist_temp = pd.DataFrame(all_hist_records)
            if 'Date' in df_hist_temp.columns:
                df_keep = df_hist_temp[df_hist_temp['Date'] != today_str]
                hist_sheet.clear()
                hist_sheet.append_row(["Date", "Ticker", "Stock_Name", "Total_Value_KRW", "Account"])
                if not df_keep.empty:
                    hist_sheet.append_rows(df_keep.values.tolist())

        if history_rows:
            hist_sheet.append_rows(history_rows)

        print(f"✅ [정산 완료] 총 {len(portfolio_rows)}개 종목의 원본 코드 유지 및 실시간 가격 반영 성공!")

    except Exception as e:
        print(f"❌ 정산 엔진 가동 중 시스템 예외 발생: {e}")

if __name__ == "__main__":
    run_portfolio_settlement()
