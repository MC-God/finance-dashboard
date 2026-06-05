import os
import gspread
from dotenv import load_dotenv
from src.sheets_client import get_sheet_client

# 환경변수 로드
load_dotenv()
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

def setup_google_sheets_template():
    print("🛠️ 구글 시트 템플릿 자동 생성을 시작합니다...")
    
    # 1. 시트 클라이언트 연결
    client = get_sheet_client()
    try:
        doc = client.open_by_key(SPREADSHEET_ID)
    except Exception as e:
        print(f"❌ 시트를 열 수 없습니다. .env 파일의 SPREADSHEET_ID를 확인하세요: {e}")
        return

    # 2. 시트별 헤더 스키마 정의 (텐베거 의견 추가)
    templates = {
        "Portfolio": ["Ticker", "Shares", "Avg_Price", "Current_Price", "1D_Return"],
        "Transaction": ["Date", "Type", "Ticker", "Shares", "Price"],
        "AI_Reports": ["Date", "Quant_Opinion", "Macro_Opinion", "Value_Opinion", "Ten_Bagger_Opinion"]
    }

    # 3. 각 시트 확인 및 템플릿 적용
    for sheet_name, headers in templates.items():
        try:
            # 시트가 이미 존재하는지 확인
            worksheet = doc.worksheet(sheet_name)
            print(f"✅ '{sheet_name}' 시트가 이미 존재합니다. 헤더를 덮어씁니다.")
        except gspread.exceptions.WorksheetNotFound:
            # 시트가 없으면 새로 생성 (기본 100행, 컬럼 수는 헤더 개수에 맞춤)
            worksheet = doc.add_worksheet(title=sheet_name, rows=100, cols=max(10, len(headers)))
            print(f"✨ '{sheet_name}' 시트를 새로 생성했습니다.")

        # 1행(A1부터 시작)에 헤더 데이터 업데이트
        worksheet.update(values=[headers], range_name="A1")
        
        # 1행(헤더)을 굵은 글씨(Bold)로 포맷팅하여 가독성 향상
        end_col = chr(ord('A') + len(headers) - 1) 
        worksheet.format(f'A1:{end_col}1', {'textFormat': {'bold': True}})
        
    # 기존에 기본으로 생성되어 있던 "시트1" (Sheet1)이 있다면 삭제
    try:
        default_sheet = doc.worksheet("시트1") 
        doc.del_worksheet(default_sheet)
        print("🗑️ 불필요한 기본 시트('시트1')를 삭제했습니다.")
    except gspread.exceptions.WorksheetNotFound:
        pass 
    except Exception:
        pass 

    print("🎉 모든 구글 시트 템플릿 세팅이 성공적으로 완료되었습니다!")

if __name__ == "__main__":
    setup_google_sheets_template()
