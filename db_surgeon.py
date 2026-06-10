import os
import time
from dotenv import load_dotenv
from src.sheets_client import get_sheet_client

load_dotenv()
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

def run_db_surgery():
    print("🏥 DB 시트 긴급 수술을 시작합니다...")
    client = get_sheet_client()
    doc = client.open_by_key(SPREADSHEET_ID)

    # 1. 코드 기반으로 파악된 가장 정확한 최신 스키마 (칼럼명)
    schema = {
        "Portfolio": ["Ticker", "Stock_Name", "Shares", "Avg_Price", "Current_Price", "1D_Return", "Currency", "Account"],
        "Transaction": ["Date", "Type", "Ticker", "Shares", "Price", "Account", "Currency"],
        "History": ["Date", "Ticker", "Stock_Name", "Total_Value_KRW", "Account"],
        "AI_Reports": ["Date", "Quant_Opinion", "Macro_Opinion", "Value_Opinion", "Ten_Bagger_Opinion"]
    }

    # 2. 누락된 헤더 강제 삽입 및 교정
    for sheet_name, headers in schema.items():
        try:
            ws = doc.worksheet(sheet_name)
            vals = ws.get_all_values()
            
            if not vals:
                ws.append_row(headers)
                print(f"✅ '{sheet_name}' 시트 생성 및 헤더 추가 완료")
            elif vals[0][0] != headers[0]:
                # 첫 행이 헤더가 아니라 실제 데이터(예: 2026-06-09)라면, 그 위에 빈 행을 만들고 헤더 삽입
                ws.insert_row(headers, index=1)
                print(f"✅ '{sheet_name}' 시트 데이터 보존 및 헤더 삽입 완료")
            else:
                # 헤더가 존재하지만 옛날 버전이라면 깔끔하게 덮어쓰기
                ws.update(values=[headers], range_name=f"A1:{chr(ord('A') + len(headers) - 1)}1")
                print(f"✅ '{sheet_name}' 시트 헤더 최신화 완료")
        except Exception as e:
            print(f"⚠️ '{sheet_name}' 교정 실패: {e}")
        time.sleep(1) # API Rate Limit 방지

    # 3. History 시트의 꼬인 Account(KRW/USD) 값 자동 복원
    try:
        port_ws = doc.worksheet("Portfolio")
        hist_ws = doc.worksheet("History")

        port_records = port_ws.get_all_records()
        # Portfolio 데이터를 순회하며 {Ticker: Account} 딕셔너리 생성
        ticker_to_account = {str(row.get("Ticker", "")).strip(): str(row.get("Account", "일반")) for row in port_records}

        hist_vals = hist_ws.get_all_values()
        if len(hist_vals) > 1:
            updates = []
            for idx, row in enumerate(hist_vals[1:], start=2): # 1행은 헤더이므로 2행부터 시작
                ticker = str(row[1]).strip()
                current_account = str(row[4]).strip() if len(row) > 4 else ""

                # 계좌명에 잘못된 통화 기호가 들어갔거나 비어있을 경우
                if current_account in ['KRW', 'USD', ''] or current_account not in ['일반', '연금']:
                    correct_account = ticker_to_account.get(ticker, "일반")
                    updates.append({'range': f'E{idx}', 'values': [[correct_account]]})

            if updates:
                hist_ws.batch_update(updates)
                print(f"🔧 History 시트의 잘못된 계좌 정보 {len(updates)}건 복원 완료!")
            else:
                print("✨ History 시트의 계좌 정보가 이미 정상입니다.")
    except Exception as e:
        print(f"⚠️ 데이터 복원 실패: {e}")

    print("🎉 DB 수술이 성공적으로 완료되었습니다!")

if __name__ == "__main__":
    run_db_surgery()
