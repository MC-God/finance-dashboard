import os
import time
from datetime import datetime
from dotenv import load_dotenv
from src.sheets_client import get_sheet_client
from src.market_data import get_stock_info
from src.ai_agent import analyze_portfolio

# 환경변수 로드
load_dotenv()
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

def run_daily_batch():
    print("🚀 [1단계] 포트폴리오 최신 주가 업데이트 시작...")
    
    client = get_sheet_client()
    doc = client.open_by_key(SPREADSHEET_ID)
    portfolio_sheet = doc.worksheet("Portfolio")
    ai_reports_sheet = doc.worksheet("AI_Reports")
    
    # 1. 시트의 모든 데이터 읽어오기
    records = portfolio_sheet.get_all_records()
    portfolio_text_list = []
    
    # 2. 각 종목별 주가 조회 및 업데이트
    for idx, row in enumerate(records):
        ticker = row.get("Ticker")
        if not ticker: 
            continue
            
        print(f"[{ticker}] 최신 데이터 조회 중...")
        market_info = get_stock_info(ticker)
        
        if market_info:
            row_idx = idx + 2 
            
            # 구글 시트 업데이트 (현재가, 1일수익률)
            portfolio_sheet.update_acell(f'D{row_idx}', market_info["current_price"])
            portfolio_sheet.update_acell(f'E{row_idx}', market_info["1d_return"])
            
            # AI에게 전달할 포트폴리오 텍스트 구성
            shares = row.get("Shares", 0)
            avg_price = row.get("Avg_Price", 0)
            portfolio_text_list.append(
                f"Ticker: {ticker} | Shares: {shares} | Avg_Price: {avg_price} | Current_Price: {market_info['current_price']} | 1D_Return: {market_info['1d_return']}%"
            )
            
            time.sleep(1) # 구글 시트 API 속도 제한 방지
            
    print("✅ 주가 업데이트 완료!\n")
    
    # AI 분석에 사용할 포트폴리오 문자열 완성
    portfolio_data_str = "\n".join(portfolio_text_list)
    
    if not portfolio_data_str.strip():
        print("⚠️ 포트폴리오에 종목이 없어 AI 분석을 건너뜁니다.")
        return

    print("🚀 [2단계] 4인 4색 AI 페르소나 분석 시작...")
    
    personas = ["quant", "macro", "value", "ten_bagger"]
    ai_results = {}
    
    for p in personas:
        print(f"🤖 [{p.upper()}] 의견 생성 중...")
        ai_results[p] = analyze_portfolio(portfolio_data_str, p)
    
    print("✅ AI 분석 완료! 시트에 저장합니다...\n")
    
    # 3. AI_Reports 시트에 새로운 행(Row) 추가
    today_date = datetime.now().strftime("%Y-%m-%d")
    new_report_row = [
        today_date,
        ai_results["quant"],
        ai_results["macro"],
        ai_results["value"],
        ai_results["ten_bagger"]
    ]
    
    # append_row를 사용하면 데이터가 있는 마지막 행 다음 줄에 자동으로 추가됩니다.
    ai_reports_sheet.append_row(new_report_row)
    
    print("🎉 오늘의 배치 작업이 모두 성공적으로 완료되었습니다!")

if __name__ == "__main__":
    run_daily_batch()
