import os
import time
from dotenv import load_dotenv
from src.sheets_client import get_sheet_client
from src.market_data import get_stock_info

# .env 파일에서 환경변수 로드
load_dotenv()
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

def update_portfolio_prices():
    print("🔄 포트폴리오 최신 주가 업데이트 시작...")
    
    # 1. 구글 시트 연결
    client = get_sheet_client()
    doc = client.open_by_key(SPREADSHEET_ID)
    sheet = doc.worksheet("Portfolio")
    
    # 2. 시트의 모든 데이터 읽어오기
    records = sheet.get_all_records()
    
    # 3. 각 종목별 주가 조회 및 업데이트
    for idx, row in enumerate(records):
        ticker = row.get("Ticker")
        if not ticker: 
            continue
            
        print(f"[{ticker}] 최신 데이터 조회 중...")
        market_info = get_stock_info(ticker)
        
        if market_info:
            # Google Sheets는 1행이 헤더이므로 데이터는 2행부터 시작 (idx + 2)
            row_idx = idx + 2 
            
            # D열(현재가)과 E열(수익률) 업데이트
            sheet.update_acell(f'D{row_idx}', market_info["current_price"])
            sheet.update_acell(f'E{row_idx}', market_info["1d_return"])
            
            # API 호출 속도 제한(Rate Limit)을 피하기 위한 1초 대기
            time.sleep(1) 
            
    print("✅ 포트폴리오 업데이트 완료! 구글 시트를 확인해보세요.")

if __name__ == "__main__":
    update_portfolio_prices()