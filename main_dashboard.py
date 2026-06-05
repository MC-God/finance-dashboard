import streamlit as st
import pandas as pd
import os
from dotenv import load_dotenv
from src.sheets_client import get_sheet_client

# --- 페이지 기본 설정 (가장 먼저 호출되어야 함) ---
st.set_page_config(page_title="AI 포트폴리오 대시보드", page_icon="📈", layout="centered")

# 환경변수 로드
load_dotenv()
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

# --- 데이터 로드 함수 (캐싱 적용) ---
# 매번 새로고침할 때마다 API를 호출하지 않도록 10분(600초) 동안 데이터를 캐싱합니다.
@st.cache_data(ttl=600)
def load_data():
    client = get_sheet_client()
    doc = client.open_by_key(SPREADSHEET_ID)
    
    # 1. 포트폴리오 데이터 가져오기
    portfolio_records = doc.worksheet("Portfolio").get_all_records()
    df_portfolio = pd.DataFrame(portfolio_records)
    
    # 2. AI 리포트 데이터 가져오기 (가장 마지막 행이 최신 데이터)
    ai_records = doc.worksheet("AI_Reports").get_all_records()
    df_ai = pd.DataFrame(ai_records)
    latest_ai_report = df_ai.iloc[-1] if not df_ai.empty else None
    
    return df_portfolio, latest_ai_report

# --- 대시보드 UI 구성 ---
st.title("📈 AI 포트폴리오 대시보드")
st.markdown("---")

try:
    with st.spinner("데이터를 불러오는 중입니다..."):
        df_portfolio, latest_ai_report = load_data()

    # [섹션 1] 포트폴리오 현황
    st.subheader("📊 현재 보유 종목 현황")
    if not df_portfolio.empty:
        # 데이터프레임을 화면에 예쁘게 렌더링
        st.dataframe(
            df_portfolio,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("현재 포트폴리오에 등록된 종목이 없습니다.")

    st.markdown("---")

    # [섹션 2] AI 페르소나 리포트 (Tabs)
    st.subheader("🤖 오늘의 AI 심층 분석")
    if latest_ai_report is not None:
        st.caption(f"📅 분석 일자: {latest_ai_report.get('Date', 'N/A')}")
        
        # 4개의 탭 생성
        tab1, tab2, tab3, tab4 = st.tabs(["📉 퀀트 (Quant)", "🌍 매크로 (Macro)", "💎 가치투자 (Value)", "🚀 텐베거 (10-Bagger)"])
        
        with tab1:
            st.info(latest_ai_report.get("Quant_Opinion", "데이터 없음"))
        with tab2:
            st.success(latest_ai_report.get("Macro_Opinion", "데이터 없음"))
        with tab3:
            st.warning(latest_ai_report.get("Value_Opinion", "데이터 없음"))
        with tab4:
            st.error(latest_ai_report.get("Ten_Bagger_Opinion", "데이터 없음"))
    else:
        st.info("아직 생성된 AI 리포트가 없습니다.")

except Exception as e:
    st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {e}")
