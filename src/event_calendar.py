import pandas as pd
import datetime
import requests
import os
import yfinance as yf
from icalendar import Calendar
from src.sheets_client import get_sheet_client

def get_major_events():
    events = []
    today = datetime.datetime.now().date()
    
    # ==========================================
    # 1. 매크로 지표 자동화 (ICS 캘린더 파싱)
    # ==========================================
    # 기본값으로 ForexFactory의 이번주 주요 경제 지표 캘린더를 사용합니다.
    # 나중에 본인만의 구글 캘린더 ICS 주소로 변경하여 완벽한 커스텀이 가능합니다.
    ics_url = os.getenv("MACRO_ICS_URL", "https://nfs.faireconomy.media/ff_calendar_thisweek.ics")
    
    try:
        res = requests.get(ics_url, timeout=5)
        if res.status_code == 200:
            cal = Calendar.from_ical(res.text)
            for component in cal.walk('vevent'):
                summary = str(component.get('summary'))
                
                # 너무 많은 이벤트가 뜨는 것을 방지하기 위해, 미국(USD) 관련 지표나 주요 이벤트만 필터링
                if "USD" in summary or "FOMC" in summary or "High" in summary:
                    dtstart = component.get('dtstart').dt
                    
                    # 날짜(Date) 타입과 시간(Datetime) 타입 호환성 처리
                    if isinstance(dtstart, datetime.datetime):
                        event_date = dtstart.date()
                    else:
                        event_date = dtstart
                        
                    # 오늘 이후의 일정만 캘린더에 추가
                    if event_date >= today:
                        events.append({
                            "Date": event_date.strftime("%Y-%m-%d"),
                            "Event": f"🌍 {summary.replace('USD -', '').strip()}",
                            "Type": "매크로",
                            "Impact": "High"
                        })
    except Exception as e:
        print(f"매크로 ICS 캘린더 동기화 실패: {e}")

    # ==========================================
    # 2. 내 보유 종목 실적 발표일 자동화 (yfinance)
    # ==========================================
    try:
        SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
        if SPREADSHEET_ID:
            doc = get_sheet_client().open_by_key(SPREADSHEET_ID)
            portfolio = doc.worksheet("Portfolio").get_all_records()
            
            # 포트폴리오에서 미국 주식(알파벳 티커)만 중복 없이 추출
            tickers = {str(row.get("Ticker", "")).replace("'", "").strip() for row in portfolio if str(row.get("Ticker", "")).replace("'", "").strip().isalpha()}
            
            for ticker in tickers:
                try:
                    cal_data = yf.Ticker(ticker).calendar
                    # yfinance에서 제공하는 캘린더 데이터 중 'Earnings Date' 추출
                    if cal_data is not None and not cal_data.empty and 'Earnings Date' in cal_data.index:
                        earnings_dates = cal_data.loc['Earnings Date']
                        if len(earnings_dates) > 0:
                            # 가장 가까운 다음 실적발표일
                            next_date = pd.to_datetime(earnings_dates[0]).date()
                            if next_date >= today:
                                events.append({
                                    "Date": next_date.strftime("%Y-%m-%d"),
                                    "Event": f"📊 {ticker} 실적 발표",
                                    "Type": "실적",
                                    "Impact": "High"
                                })
                except Exception:
                    continue # 조회 불가능한 종목은 스킵
    except Exception as e:
        print(f"포트폴리오 실적 연동 실패: {e}")
        
    # ==========================================
    # 3. 데이터 후처리 (정렬 및 중복 제거)
    # ==========================================
    if not events:
        events.append({
            "Date": (today + datetime.timedelta(days=1)).strftime("%Y-%m-%d"),
            "Event": "📅 예정된 주요 일정이 없습니다.",
            "Type": "안내",
            "Impact": "Low"
        })

    df = pd.DataFrame(events)
    df['Date'] = pd.to_datetime(df['Date'])
    
    # 날짜 오름차순으로 정렬하고, 중복된 이벤트 제거
    df = df.sort_values('Date').drop_duplicates(subset=['Date', 'Event'])
    return df
