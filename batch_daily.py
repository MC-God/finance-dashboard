import os
import time
import sys
from datetime import datetime
from dotenv import load_dotenv
from src.sheets_client import get_sheet_client
from src.market_data import get_stock_info
from src.ai_agent import analyze_portfolio

# 환경변수 로드
load_dotenv()
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

def run_daily_batch(mode="all"):
    """
    mode='kr' : 한국 주식(숫자 티커)만 주가 업데이트 후 종료
    mode='us' : 미국 주식(영문 티커) 주가 업데이트 후 전체 포트폴리오 AI 분석 진행
    """
    print(f"🚀 일일 배치 작업 시작 (실행 모드: {mode})")
    
    client = get_sheet_client()
    doc = client.open_by_key(SPREADSHEET_ID)
    portfolio_sheet = doc.worksheet("Portfolio")
    
    records = portfolio_sheet.get_all_records()
    portfolio_text_list = []
    
    print("📊 [1단계] 포트폴리오 주가 업데이트...")
    for idx, row in enumerate(records):
        ticker = str(row.get("Ticker"))
        if not ticker or ticker.strip() == "": 
            continue
            
        is_kr = ticker.isdigit() # 티커가 숫자면 한국 주식으로 판별
        
        # 모드별 실행 필터링
        if mode == "kr" and not is_kr:
            continue # 한국장 모드일 땐 미국 주식 건너뜀
        if mode == "us" and is_kr:
            # 미국장 모드일 땐 한국 주식 조회를 건너뛰지만, AI 분석을 위해 텍스트는 수집함
            shares = row.get("Shares", 0)
            avg_price = row.get("Avg_Price", 0)
            c_price = row.get("Current_Price", 0)
            d_return = row.get("1D_Return", 0)
            portfolio_text_list.append(f"Ticker: {ticker} | Shares: {shares} | Avg_Price: {avg_price} | Current_Price: {c_price} | 1D_Return: {d_return}%")
            continue

        print(f"[{ticker}] 최신 데이터 조회 중...")
        market_info = get_stock_info(ticker)
        
        if market_info:
            row_idx = idx + 2 
            portfolio_sheet.update_acell(f'D{row_idx}', market_info["current_price"])
            portfolio_sheet.update_acell(f'E{row_idx}', market_info["1d_return"])
            
            shares = row.get("Shares", 0)
            avg_price = row.get("Avg_Price", 0)
            portfolio_text_list.append(
                f"Ticker: {ticker} | Shares: {shares} | Avg_Price: {avg_price} | Current_Price: {market_info['current_price']} | 1D_Return: {market_info['1d_return']}%"
            )
            time.sleep(1)
            
    print("✅ 주가 업데이트 완료!\n")
    
    # 한국장 모드면 여기서 스크립트 종료
    if mode == "kr":
        print("🛑 한국 주식 업데이트가 완료되었습니다. AI 리포트는 내일 아침 미국장 마감 후에 생성됩니다.")
        return

    # --- 미국장(또는 전체) 모드일 경우 AI 분석 실행 ---
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
    
    ai_reports_sheet = doc.worksheet("AI_Reports")
    today_date = datetime.now().strftime("%Y-%m-%d")
    new_report_row = [
        today_date,
        ai_results["quant"],
        ai_results["macro"],
        ai_results["value"],
        ai_results["ten_bagger"]
    ]
    ai_reports_sheet.append_row(new_report_row)
    print("🎉 배치가 모두 성공적으로 완료되었습니다!")

if __name__ == "__main__":
    # 실행 시 뒤에 붙는 인자(kr, us)를 받아 모드 설정
    run_mode = "all"
    if len(sys.argv) > 1:
        run_mode = sys.argv[1].lower()
    run_daily_batch(run_mode)
