import FinanceDataReader as fdr
import pandas as pd
from datetime import datetime, timedelta
import math

def get_stock_info(ticker):
    """
    FinanceDataReader를 활용하여 한/미 주식의 현재가와 1일 변동률을 가져옵니다.
    - 한국 주식: '005930' (숫자 6자리)
    - 미국 주식: 'NVDA', 'AAPL' 등
    """
    try:
        # 휴장일을 대비해 넉넉하게 최근 7일치 데이터를 요청
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        # 티커가 정수형으로 들어올 경우를 대비해 문자열로 변환 (예: 5930 -> '005930')
        ticker_str = str(ticker).zfill(6) if str(ticker).isdigit() else str(ticker)
        
        df = fdr.DataReader(ticker_str, start_date, end_date)
        
        if df.empty or len(df) < 2:
            print(f"⚠️ [{ticker_str}] 데이터를 충분히 불러오지 못했습니다.")
            return None
            
        current_price = float(df['Close'].iloc[-1])
        prev_price = float(df['Close'].iloc[-2])
        
        if math.isnan(current_price) or math.isnan(prev_price):
            print(f"⚠️ [{ticker_str}] 결측치(NaN)가 감지되어 건너뜁니다.")
            return None
            
        # 1일 수익률 계산 (%)
        daily_return_pct = ((current_price - prev_price) / prev_price) * 100
        
        return {
            "ticker": ticker_str,
            "current_price": round(current_price, 2),
            "1d_return": round(daily_return_pct, 2)
        }
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return None

# --- 테스트 실행 블록 ---
if __name__ == "__main__":
    # 한국 주식(삼성전자)과 미국 주식(엔비디아) 동시 테스트
    test_tickers = ["005930", "NVDA"] 
    
    for t in test_tickers:
        data = get_stock_info(t)
        if data:
            print(f"[{data['ticker']}] 현재가: {data['current_price']} (1일 변동: {data['1d_return']}%)")
