import streamlit as st
import pandas as pd
import os
import json
from dotenv import load_dotenv
from src.sheets_client import get_sheet_client

# --- 페이지 기본 설정 (가장 먼저 호출) ---
st.set_page_config(page_title="AI 포트폴리오 대시보드", page_icon="📈", layout="centered")

# --- 클라우드 배포용 환경변수 및 인증서 세팅 ---
# Streamlit Cloud의 Secrets에서 구글 인증서를 가져와 임시 파일로 생성합니다.
if not os.path.exists("credentials.json"):
    try:
        google_creds = st.secrets["GOOGLE_CREDENTIALS"]
        with open("credentials.json", "w") as f:
            f.write(google_creds)
    except Exception:
        pass # 로컬 환경에서는 기존 .env와 credentials.json을 그대로 사용함

load_dotenv()
# 로컬(.env)에 없으면 클라우드(st.secrets)에서 SPREADSHEET_ID를 가져옴
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID") or st.secrets.get("SPREADSHEET_ID")

# --- 데이터 로드 함수 (캐싱 적용) ---
@st.cache_data(ttl=600)
def load_data():
    client = get_sheet_client()
    doc = client.open_by_key(SPREADSHEET_ID)
    
    portfolio_records = doc.worksheet("Portfolio").get_all_records()
    df_portfolio = pd.DataFrame(portfolio_records)
    
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

    st.subheader("📊 현재 보유 종목 현황")
    if not df_portfolio.empty:
        st.dataframe(df_portfolio, use_container_width=True, hide_index=True)
    else:
        st.info("현재 포트폴리오에 등록된 종목이 없습니다.")

    st.markdown("---")

    st.subheader("🤖 오늘의 AI 심층 분석")
    if latest_ai_report is not None:
        st.caption(f"📅 분석 일자: {latest_ai_report.get('Date', 'N/A')}")
        
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
