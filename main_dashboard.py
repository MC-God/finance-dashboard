import streamlit as st
import pandas as pd
import os
import json
from dotenv import load_dotenv
from src.sheets_client import get_sheet_client

# --- 페이지 기본 설정 (와이드 모드로 변경하여 프로페셔널함 강조) ---
st.set_page_config(page_title="Hedge Fund Style Cockpit", page_icon="🏦", layout="wide")

# --- 클라우드 배포용 환경변수 및 인증서 세팅 ---
if "google_credentials" in st.secrets:
    try:
        creds_dict = dict(st.secrets["google_credentials"])
        with open("credentials.json", "w", encoding="utf-8") as f:
            json.dump(creds_dict, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"인증서 동기화 중 오류 발생: {e}")

load_dotenv()
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID") or st.secrets.get("SPREADSHEET_ID")

# --- 데이터 로드 함수 (캐싱 적용) ---
@st.cache_data(ttl=300)
def load_data():
    client = get_sheet_client()
    doc = client.open_by_key(SPREADSHEET_ID)
    
    portfolio_records = doc.worksheet("Portfolio").get_all_records()
    df_portfolio = pd.DataFrame(portfolio_records)
    
    # 만약 Account 컬럼이 비어있다면 '일반'으로 기본값 채우기
    if not df_portfolio.empty and 'Account' not in df_portfolio.columns:
        df_portfolio['Account'] = '일반'
    elif not df_portfolio.empty:
        df_portfolio['Account'] = df_portfolio['Account'].replace("", "일반")
        
    ai_records = doc.worksheet("AI_Reports").get_all_records()
    df_ai = pd.DataFrame(ai_records)
    latest_ai_report = df_ai.iloc[-1] if not df_ai.empty else None
    
    return df_portfolio, latest_ai_report

# --- 대시보드 UI 구성 ---
st.title("🏦 포트폴리오 모니터링 콕핏 (Cockpit)")
st.markdown("---")

try:
    with st.spinner("실시간 시장 데이터 동기화 중..."):
        df_portfolio, latest_ai_report = load_data()

    if not df_portfolio.empty:
        # --- 상단 KPI 전광판 메트릭 연산 ---
        # 수치형 데이터 전처리 (콤마 제거 등)
        df_portfolio['Shares'] = pd.to_numeric(df_portfolio['Shares'], errors='coerce').fillna(0)
        df_portfolio['Current_Price'] = pd.to_numeric(df_portfolio['Current_Price'], errors='coerce').fillna(0)
        
        # 1D_Return 평균 및 총자산 계산 (임시 가치 계산: 평단가 기능 활용 가능)
        df_portfolio['Total_Value'] = df_portfolio['Shares'] * df_portfolio['Current_Price']
        
        total_asset = df_portfolio['Total_Value'].sum()
        normal_asset = df_portfolio[df_portfolio['Account'] == '일반']['Total_Value'].sum()
        pension_asset = df_portfolio[df_portfolio['Account'] == '연금']['Total_Value'].sum()

        # --- 메트릭 전광판 배치 ---
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(label="💰 총 자산 (Total Portfolio)", value=f"{total_asset:,.0f} 원")
        with col2:
            st.metric(label="💵 일반 계좌 자산", value=f"{normal_asset:,.0f} 원")
        with col3:
            st.metric(label="🛡️ 연금 계좌 자산 (세제혜택)", value=f"{pension_asset:,.0f} 원")
            
        st.markdown("---")

        # --- 메인 영역: 계좌별 분리 탭 조율 ---
        st.subheader("📊 자산 보유 현황 및 배분")
        account_tab1, account_tab2, account_tab3 = st.tabs(["전체 보기", "일반 주식계좌", "연금저축/IRP"])
        
        with account_tab1:
            st.dataframe(df_portfolio, use_container_width=True, hide_index=True)
        with account_tab2:
            df_normal = df_portfolio[df_portfolio['Account'] == '일반']
            st.dataframe(df_normal, use_container_width=True, hide_index=True)
        with account_tab3:
            df_pension = df_portfolio[df_portfolio['Account'] == '연금']
            st.dataframe(df_pension, use_container_width=True, hide_index=True)
            
    else:
        st.info("현재 포트폴리오에 등록된 종목이 없습니다. 텔레그램을 통해 등록해 주세요.")

    st.markdown("---")

    # --- 하단 영역: AI 애널리스트 리포트 ---
    st.subheader("🤖 AI 리포트 브리핑 소룸")
    if latest_ai_report is not None:
        st.caption(f"📅 릴리즈 일자: {latest_ai_report.get('Date', 'N/A')}")
        
        tab1, tab2, tab3, tab4 = st.tabs(["📉 퀀트 (Quant)", "🌍 매크로 (Macro)", "💎 가치투자 (Value)", "🚀 텐베거 (10-Bagger)"])
        with tab1:
            st.markdown(f"### 수석 퀀트 애널리스트 의견\n{latest_ai_report.get('Quant_Opinion', '데이터 없음')}")
        with tab2:
            st.markdown(f"### 글로벌 매크로 포지셔닝\n{latest_ai_report.get('Macro_Opinion', '데이터 없음')}")
        with tab3:
            st.markdown(f"### 펀더멘털 및 안전마진 조언\n{latest_ai_report.get('Value_Opinion', '데이터 없음')}")
        with tab4:
            st.markdown(f"### 혁신 기술 및 텐베거 탐색\n{latest_ai_report.get('Ten_Bagger_Opinion', '데이터 없음')}")

except Exception as e:
    st.error(f"데이터 파일 렌더링 중 시스템 예외 발생: {e}")
