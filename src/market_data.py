import yfinance as yf
import pandas as pd

def get_stock_info(ticker):
    """
    특정 종목의 현재가와 1일 변동률을 가져옵니다.
    추후 1M, 1Y 수익률 및 거시 지표(환율/금리) 로직이 추가될 함수입니다.
    """
    try:
        stock = yf.Ticker(ticker)
        # 최근 5일치 데이터를 가져와서 어제/오늘 가격 비교
        hist = stock.history(period="5d") 
        
        if len(hist) < 2:
            return None
            
        current_price = hist['Close'].iloc[-1]
        prev_price = hist['Close'].iloc[-2]
        
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
    # 개별 기술주 및 섹터 ETF 테스트
    test_tickers = ["NVDA", "SOXX"] 
    
    for t in test_tickers:
        data = get_stock_info(t)
        if data:
            print(f"[{data['ticker']}] 현재가: ${data['current_price']} (1일 변동: {data['1d_return']}%)")