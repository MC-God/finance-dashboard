import yfinance as yf
import pandas as pd
import math

def get_stock_info(ticker):
    """
    특정 종목의 현재가와 1일 변동률을 가져옵니다.
    """
    try:
        stock = yf.Ticker(ticker)
        # 최근 5일치 데이터를 가져와서 어제/오늘 가격 비교
        hist = stock.history(period="5d") 
        
        if len(hist) < 2:
            return None
            
        # numpy 자료형을 파이썬 기본 float 형으로 강제 변환
        current_price = float(hist['Close'].iloc[-1])
        prev_price = float(hist['Close'].iloc[-2])
        
        # yfinance가 NaN(결측치)을 반환할 경우 업데이트를 건너뛰도록 처리
        if math.isnan(current_price) or math.isnan(prev_price):
            print(f"⚠️ [{ticker}] 유효하지 않은 주가 데이터(NaN)가 감지되어 건너뜁니다.")
            return None
            
        # 1일 수익률 계산 (%)
        daily_return_pct = ((current_price - prev_price) / prev_price) * 100
        
        return {
            "ticker": ticker,
            "current_price": round(current_price, 2),
            "1d_return": round(daily_return_pct, 2)
        }
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return None

# --- 테스트 실행 블록 ---
if __name__ == "__main__":
    test_tickers = ["NVDA", "SOXX"] 
    
    for t in test_tickers:
        data = get_stock_info(t)
        if data:
            print(f"[{data['ticker']}] 현재가: ${data['current_price']} (1일 변동: {data['1d_return']}%)")
