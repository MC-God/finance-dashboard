import gspread
from google.oauth2.service_account import Credentials
import os

def get_sheet_client():
    """Google Sheets API 클라이언트를 인증하고 반환합니다."""
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    
    # 루트 디렉토리의 credentials.json 경로 지정
    creds_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'credentials.json')
    
    if not os.path.exists(creds_path):
        raise FileNotFoundError("credentials.json 파일이 최상위 폴더에 없습니다!")
        
    credentials = Credentials.from_service_account_file(creds_path, scopes=scopes)
    client = gspread.authorize(credentials)
    
    return client

# --- 테스트 실행 블록 ---
if __name__ == "__main__":
    try:
        client = get_sheet_client()
        print("✅ 구글 시트 API 인증 성공!")
    except Exception as e:
        print(f"❌ 인증 실패: {e}")