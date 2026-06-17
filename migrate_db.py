# migrate_db.py
import os
from dotenv import load_dotenv
from src.sheets_client import get_sheet_client

load_dotenv()
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

def run_migration():
    print("🚀 구글 시트 마이그레이션을 시작합니다...")
    client = get_sheet_client()
    doc = client.open_by_key(SPREADSHEET_ID)

    # 1. Realized_PnL 시트가 없으면 생성
    try:
        pnl_sheet = doc.worksheet("Realized_PnL")
        print("✅ 'Realized_PnL' 시트가 이미 존재합니다.")
    except:
        pnl_sheet = doc.add_worksheet(title="Realized_PnL", rows="1000", cols="10")
        print("✅ 'Realized_PnL' 시트를 새로 생성했습니다.")

    # 2. 헤더 초기화 (데이터 꼬임 방지)
    pnl_header = ["Date", "Ticker", "Account", "Currency", "Sold_Shares", "Sell_Price", "Avg_Cost", "Realized_PnL"]
    pnl_sheet.clear()
    pnl_sheet.append_row(pnl_header)
    print("✅ 'Realized_PnL' 헤더 셋업 완료.")
    
    print("🎉 DB 마이그레이션이 완료되었습니다! 이제 구글 시트에 직접 들어갈 필요가 없습니다.")

if __name__ == "__main__":
    run_migration()
