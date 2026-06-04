import os
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from dotenv import load_dotenv

# 현재 스크립트(db 폴더)의 상위 폴더(FINANCE-DASHBOARD)를 동적으로 찾음
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 루트 경로의 .env 파일 로드
load_dotenv(dotenv_path=os.path.join(BASE_DIR, '.env'))

class SheetsClient:
    def __init__(self):
        # 구글 시트 및 드라이브 접근을 위한 인증 스코프
        self.scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        # 파일명 수정 반영 (credentials.json)
        self.credential_path = os.path.join(BASE_DIR, "credentials.json")
        
        if not os.path.exists(self.credential_path):
            raise FileNotFoundError(
                f"credentials.json 파일을 찾을 수 없습니다. 경로를 확인해주세요: {self.credential_path}"
            )
            
        # 인증 객체 생성 및 gspread 클라이언트 인스턴스화
        self.credentials = Credentials.from_service_account_file(
            self.credential_path, 
            scopes=self.scopes
        )
        self.client = gspread.authorize(self.credentials)
        
        # 시트 이름 수정 반영 (Finance_DB)
        self.spreadsheet_name = os.getenv("GOOGLE_SHEET_NAME", "Finance_DB")
        
        try:
            # 이름으로 구글 스프레드시트 열기
            self.sheet = self.client.open(self.spreadsheet_name)
        except gspread.exceptions.SpreadsheetNotFound:
            raise gspread.exceptions.SpreadsheetNotFound(
                f"\n[{self.spreadsheet_name}] 스프레드시트를 찾을 수 없습니다.\n"
                "1. 구글 스프레드시트의 이름이 일치하는지 확인하세요.\n"
                "2. credentials.json 파일 안의 'client_email' 주소로 해당 시트가 '편집자' 권한으로 공유되었는지 확인하세요."
            )

    def get_sheet_data(self, worksheet_name: str) -> pd.DataFrame:
        """지정한 워크시트(탭)의 데이터를 Pandas DataFrame으로 가져옵니다."""
        try:
            worksheet = self.sheet.worksheet(worksheet_name)
            records = worksheet.get_all_records()
            return pd.DataFrame(records)
        except gspread.exceptions.WorksheetNotFound:
            print(f"[{worksheet_name}] 워크시트를 찾을 수 없습니다.")
            return pd.DataFrame()
        except Exception as e:
            print(f"데이터를 가져오는 중 오류 발생 ({worksheet_name}): {e}")
            return pd.DataFrame()

    def update_sheet_from_df(self, worksheet_name: str, df: pd.DataFrame):
        """Pandas DataFrame 데이터를 지정한 워크시트에 덮어씁니다."""
        try:
            worksheet = self.sheet.worksheet(worksheet_name)
            worksheet.clear()
            # 구글 시트 에러 방지를 위해 NaN 데이터를 빈 문자열로 처리
            df = df.fillna('')
            # gspread v6+ 호환 리스트 업데이트
            worksheet.update(values=[df.columns.values.tolist()] + df.values.tolist())
        except Exception as e:
            print(f"데이터 업데이트 중 오류 발생 ({worksheet_name}): {e}")

    def append_row(self, worksheet_name: str, row_data: list):
        """지정한 워크시트의 맨 아래에 한 줄의 데이터를 추가합니다."""
        try:
            worksheet = self.sheet.worksheet(worksheet_name)
            worksheet.append_row(row_data)
        except Exception as e:
            print(f"데이터 추가 중 오류 발생 ({worksheet_name}): {e}")

# 자체 테스트용 코드 (이 파일만 직접 실행했을 때 작동)
if __name__ == "__main__":
    try:
        db = SheetsClient()
        print("✅ 구글 스프레드시트 연결 성공!")
        
        df_portfolio = db.get_sheet_data("portfolio")
        if df_portfolio.empty:
            print("⚠️ 'portfolio' 탭의 데이터가 없거나 탭이 존재하지 않습니다.")
        else:
            print("\n[현재 포트폴리오 데이터 (최상단 5개)]")
            print(df_portfolio.head())
            
    except Exception as e:
        print(f"❌ 연결 실패: {e}")