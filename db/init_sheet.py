import os
import sys
import pandas as pd
import gspread

# 현재 스크립트 위치에서 최상위 루트 경로를 시스템 패스에 추가
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

# 작성해둔 SheetsClient 불러오기
from db.sheets_client import SheetsClient

def setup_initial_sheet():
    try:
        db = SheetsClient()
        
        # 1. portfolio 탭 존재 여부 확인 및 없으면 자동 생성
        try:
            worksheet = db.sheet.worksheet("portfolio")
            print("✅ 'portfolio' 탭이 확인되었습니다.")
        except gspread.exceptions.WorksheetNotFound:
            print("⚠️ 'portfolio' 탭이 없습니다. 코드로 자동 생성합니다...")
            db.sheet.add_worksheet(title="portfolio", rows=100, cols=20)
            
        # 2. 초기 헤더 및 샘플 데이터 구성 (Pandas DataFrame 활용)
        sample_data = {
            "ticker": ["NVDA", "005930"],
            "stock_name": ["엔비디아", "삼성전자"],
            "market": ["US", "KR"],
            "purchase_price": [120.50, 72000.0],
            "quantity": [50, 100],
            "current_price": [125.00, 75000.0], # 테스트용 임시 현재가
            "sector": ["Semiconductor", "Semiconductor"]
        }
        df = pd.DataFrame(sample_data)
        
        # 3. 시트에 데이터 덮어쓰기
        db.update_sheet_from_df("portfolio", df)
        print("✅ 헤더 및 샘플 데이터 세팅이 구글 시트에 완벽하게 적용되었습니다!")
        
    except Exception as e:
        print(f"❌ 설정 중 오류 발생: {e}")

if __name__ == "__main__":
    setup_initial_sheet()