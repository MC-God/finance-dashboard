import os
import sys
import pandas as pd

# 최상위 경로를 시스템 패스에 추가하여 db 모듈을 가져올 수 있게 함
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from db.sheets_client import SheetsClient

class PortfolioManager:
    def __init__(self):
        # DB 클라이언트 인스턴스화
        self.db = SheetsClient()

    def get_calculated_portfolio(self) -> dict:
        """
        포트폴리오 데이터를 불러와 각종 수익률 지표를 계산하여 반환합니다.
        """
        df = self.db.get_sheet_data("portfolio")
        
        if df.empty:
            return {"status": "empty", "message": "포트폴리오 데이터가 없습니다."}

        # 구글 시트에서 가져온 데이터가 문자열일 수 있으므로 숫자형으로 강제 변환
        df['purchase_price'] = pd.to_numeric(df['purchase_price'], errors='coerce')
        df['current_price'] = pd.to_numeric(df['current_price'], errors='coerce')
        df['quantity'] = pd.to_numeric(df['quantity'], errors='coerce')

        # 개별 종목 투자금액 및 평가금액 계산
        df['invested_amount'] = df['purchase_price'] * df['quantity']
        df['current_value'] = df['current_price'] * df['quantity']
        
        # 개별 종목 평가손익 및 수익률 계산
        df['profit'] = df['current_value'] - df['invested_amount']
        df['return_rate'] = (df['profit'] / df['invested_amount']) * 100

        # 전체 포트폴리오 합계 계산
        total_invested = df['invested_amount'].sum()
        total_current = df['current_value'].sum()
        total_profit = df['profit'].sum()
        total_return_rate = (total_profit / total_invested) * 100 if total_invested > 0 else 0

        return {
            "status": "success",
            "total_invested": total_invested,
            "total_current": total_current,
            "total_profit": total_profit,
            "total_return_rate": total_return_rate,
            "dataframe": df  # AI 분석이나 시각화에 사용할 원본+계산된 데이터프레임
        }

    def get_summary_text(self) -> str:
        """
        텔레그램 봇으로 전송할 깔끔한 텍스트 형태의 포트폴리오 요약본을 생성합니다.
        """
        data = self.get_calculated_portfolio()
        
        if data["status"] == "empty":
            return "📊 <b>포트폴리오 현황</b>\n\n현재 등록된 주식 데이터가 없습니다. 구글 시트를 확인해주세요."

        # 전체 요약 텍스트 구성
        total_current = data['total_current']
        total_profit = data['total_profit']
        total_return_rate = data['total_return_rate']
        
        # 수익률에 따라 이모지 및 부호 변경
        sign = "+" if total_profit > 0 else ""
        emoji = "📈" if total_profit > 0 else "📉"
        
        text = f"📊 <b>내 주식 포트폴리오 현황</b>\n\n"
        text += f"💰 <b>총 평가 금액:</b> {total_current:,.0f}원 (또는 달러)\n"
        text += f"💵 <b>총 평가 손익:</b> {sign}{total_profit:,.0f} ({emoji} {total_return_rate:.2f}%)\n"
        text += f"━━━━━━━━━━━━━━━━━━\n"

        # 개별 종목 현황 추가
        df = data['dataframe']
        for _, row in df.iterrows():
            stock_name = row['stock_name']
            ticker = row['ticker']
            profit = row['profit']
            rate = row['return_rate']
            
            s_sign = "+" if profit > 0 else ""
            s_emoji = "🔴" if profit > 0 else "🔵" # 한국 주식 기준 (빨강 상승, 파랑 하락)
            
            text += f"{s_emoji} <b>{stock_name} ({ticker})</b>\n"
            text += f"  수익: {s_sign}{profit:,.0f} ({rate:.2f}%)\n"
        
        return text

# 자체 테스트용 코드
if __name__ == "__main__":
    manager = PortfolioManager()
    print("✅ 포트폴리오 매니저 테스트 실행\n")
    print(manager.get_summary_text())