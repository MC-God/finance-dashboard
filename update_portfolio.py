import os
import datetime
import pandas as pd
import FinanceDataReader as fdr
from dotenv import load_dotenv
from src.sheets_client import get_sheet_client

# 환경변수 로드
load_dotenv()
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

def run_portfolio_settlement():
    print(f"[{datetime.datetime.now()}] 🔄 자산 정산 및 시장 시세 동기화를 가동합니다...")
    
    try:
        sheet_client = get_sheet_client()
        doc = sheet_client.open_by_key(SPREADSHEET_ID)
        
        # 1. Transaction(거래 기록) 시트 데이터 로드
        tx_sheet = doc.worksheet("Transaction")
        tx_records = tx_sheet.get_all_records()
        
        if not tx_records:
            print("⚠️ 거래 기록이 비어있어 정산을 종료합니다.")
            return
            
        df_tx = pd.DataFrame(tx_records)
        
        # 2. 종목별 / 계좌별 / 통화별 잔고 및 평단가 연산
        holdings = {}
        for _, row in df_tx.iterrows():
            ticker = str(row.get('Ticker', '')).strip()
            action = row.get('Action', '').strip()
            shares = float(row.get('Shares', 0))
            price = float(row.get('Price', 0))
            currency = row.get('Currency', 'KRW').strip()
            account = row.get('Account', '일반').strip()
            
            if not ticker:
                continue
                
            key = (ticker, account, currency)
            if key not in holdings:
                holdings[key] = {'shares': 0.0, 'total_cost': 0.0}
                
            if action == '매수':
                holdings[key]['shares'] += shares
                holdings[key]['total_cost'] += (shares * price)
            elif action == '매도':
                if holdings[key]['shares'] > 0:
                    # 매도 시 기존 평단가를 유지하면서 수량과 cost를 비례 차감
                    avg_p = holdings[key]['total_cost'] / holdings[key]['shares']
                    holdings[key]['shares'] -= shares
                    holdings[key]['total_cost'] = holdings[key]['shares'] * avg_p
                else:
                    holdings[key]['shares'] -= shares

        # 3. 각 종목별 FinanceDataReader 시세 매칭
        portfolio_rows = []
        today_str = datetime.date.today().strftime('%Y-%m-%d')
        start_str = (datetime.date.today() - datetime.timedelta(days=10)).strftime('%Y-%m-%d')

        for key, data in holdings.items():
            ticker, account, currency = key
            shares = data['shares']
            
            # 전량 매도되어 잔고가 없는 종목은 포트폴리오 노출에서 제외
            if shares <= 0:
                continue
                
            avg_price = data['total_cost'] / shares if shares > 0 else 0
            current_price = avg_price
            one_day_return = "0.0%"
            
            # FDR 시세 엔진 가동
            try:
                # 최근 10일치 데이터를 가져와 가장 최신 영업일(마지막 줄)과 직전 영업일(그 앞줄) 비교
                df_stock = fdr.DataReader(ticker, start=start_str)
                if not df_stock.empty and len(df_stock) >= 1:
                    current_price = float(df_stock.iloc[-1]['Close'])
                    if len(df_stock) >= 2:
                        prev_close = float(df_stock.iloc[-2]['Close'])
                        raw_return = ((current_price - prev_close) / prev_close) * 100
                        one_day_return = f"{raw_return:+.2f}%"
                    else:
                        one_day_return = "0.00%"
            except Exception as e:
                print(f"⚠️ [{ticker}] 시세 조회 실패 (구글 기본 단가 대체): {e}")

            portfolio_rows.append([
                ticker,
                int(shares) if shares.is_integer() else shares,
                round(avg_price, 2),
                current_price,
                one_day_return,
                currency,
                account
            ])

        # 4. Portfolio 시트에 정산 결과 업데이트 (오버라이트)
        port_sheet = doc.worksheet("Portfolio")
        
        # 기존 데이터 완전히 포맷팅 (헤더 제외)
        port_sheet.clear()
        
        # 새 헤더 및 데이터 세팅
        headers = ["Ticker", "Shares", "Avg_Price", "Current_Price", "1D_Return", "Currency", "Account"]
        port_sheet.append_row(headers)
        
        if portfolio_rows:
            port_sheet.append_rows(portfolio_rows)
            
        print(f"✅ 포트폴리오 정산 완료: 총 {len(portfolio_rows)}개 종목 갱신 성공.")

    except Exception as e:
        print(f"❌ 정산 중 치명적 예외 발생: {e}")

if __name__ == "__main__":
    run_portfolio_settlement()
