import pandas as pd
import datetime

def get_major_events():
    """
    글로벌 주요 매크로, 중앙은행 금리결정 및 빅테크 핵심 이벤트를 반환합니다.
    * 현재 연도(2026년) 기준 주요 일정 데이터베이스
    """
    events = [
        # 🇺🇸 미국 FOMC (2026 예상 일정)
        {"Date": "2026-01-28", "Event": "🇺🇸 연준 FOMC 금리결정", "Type": "매크로", "Impact": "High"},
        {"Date": "2026-03-18", "Event": "🇺🇸 연준 FOMC 금리결정 (점도표)", "Type": "매크로", "Impact": "High"},
        {"Date": "2026-04-29", "Event": "🇺🇸 연준 FOMC 금리결정", "Type": "매크로", "Impact": "Medium"},
        {"Date": "2026-06-17", "Event": "🇺🇸 연준 FOMC 금리결정 (점도표)", "Type": "매크로", "Impact": "High"},
        {"Date": "2026-07-29", "Event": "🇺🇸 연준 FOMC 금리결정", "Type": "매크로", "Impact": "Medium"},
        {"Date": "2026-09-16", "Event": "🇺🇸 연준 FOMC 금리결정 (점도표)", "Type": "매크로", "Impact": "High"},
        {"Date": "2026-11-04", "Event": "🇺🇸 연준 FOMC 금리결정", "Type": "매크로", "Impact": "Medium"},
        {"Date": "2026-12-16", "Event": "🇺🇸 연준 FOMC 금리결정 (점도표)", "Type": "매크로", "Impact": "High"},
        
        # 🇰🇷 한국은행 금통위 (2026 예상 일정)
        {"Date": "2026-01-15", "Event": "🇰🇷 한국은행 금통위", "Type": "매크로", "Impact": "Medium"},
        {"Date": "2026-02-26", "Event": "🇰🇷 한국은행 금통위", "Type": "매크로", "Impact": "Medium"},
        {"Date": "2026-04-16", "Event": "🇰🇷 한국은행 금통위", "Type": "매크로", "Impact": "Medium"},
        
        # 🇯🇵 BOJ & 🇪🇺 ECB (핵심 일정 발췌)
        {"Date": "2026-01-23", "Event": "🇯🇵 일본 BOJ 금리결정", "Type": "매크로", "Impact": "High"},
        {"Date": "2026-03-12", "Event": "🇪🇺 유럽 ECB 금리결정", "Type": "매크로", "Impact": "High"},
        
        # 💻 글로벌 빅테크 및 산업 이벤트
        {"Date": "2026-01-09", "Event": "🌐 CES 2026 개막", "Type": "산업/기술", "Impact": "Medium"},
        {"Date": "2026-05-12", "Event": "🟩 Google I/O (예상)", "Type": "빅테크", "Impact": "Medium"},
        {"Date": "2026-06-08", "Event": "🍎 Apple WWDC (예상)", "Type": "빅테크", "Impact": "High"},
        {"Date": "2026-08-26", "Event": "🟩 Nvidia 2분기 실적발표 (예상)", "Type": "실적", "Impact": "High"},
        {"Date": "2026-10-22", "Event": "🚗 Tesla 배터리/AI 데이 (예상)", "Type": "빅테크", "Impact": "High"},
    ]
    
    df = pd.DataFrame(events)
    df['Date'] = pd.to_datetime(df['Date'])
    return df
