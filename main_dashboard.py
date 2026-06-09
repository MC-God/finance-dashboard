import streamlit as st
import pandas as pd
import os
import json
import requests
from dotenv import load_dotenv
from src.sheets_client import get_sheet_client

# --- 페이지 기본 설정 ---
st.set_page_config(page_title="Hedge Fund Style Cockpit", page_icon="🏦", layout="wide")

if "google_credentials" in st.secrets:
    try:
        creds_dict = dict(st.secrets["google_credentials"])
        with open("credentials.json", "w", encoding="utf-8") as f:
            json.dump(creds_dict, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"인증서 동기화 중 오류 발생: {e}")

load_dotenv()
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID") or st.secrets.get("SPREADSHEET_ID")

# --- 💡 환율 가져오기 함수 (실시간 API 연동 예시 또는 안전용 Fallback 1,350원) ---
def get_usd_krw_rate():
    try:
        # 가볍고 인증이 필요 없는 오픈 API 이용 실시간 환율 수집 시도
        res = requests.get("https://open.er-api.com/v6/latest/USD", timeout=3)
        if res.status_code == 200:
            return float(res.json()["rates"]["KRW"])
    except Exception:
        pass
    return 1350.0  # 네트워크 요인으로 실패 시 안전 안전망용 고시환율 고정값

# --- 데이터 로드 함수 ---
@st.cache_data(ttl=300)
def load_data():
    client = get_sheet_client()
    doc = client.open_by_key(SPREADSHEET_ID)
    
    portfolio_records = doc.worksheet("Portfolio").get_all_records()
    df_portfolio = pd.DataFrame(portfolio_records)
    
    if not df_portfolio.empty:
        # 1. 계좌 정보 빈칸 처리
        if 'Account' not in df_portfolio.columns:
            df_portfolio['Account'] = '일반'
        else:
            df_portfolio['Account'] = df_portfolio['Account'].replace("", "일반")
            
        # 2. 💡 통화 정보 예외처리 및 자동 추론 (하위호환 장치)
        if 'Currency' not in df_portfolio.columns:
            # 티커가 영어 알파벳 문자로만 되어 있으면 USD, 아니면(숫자코드) KRW 자동 분류
            df_portfolio['Currency'] = df_portfolio['Ticker'].apply(lambda x: 'USD' if str(x).isalpha() else 'KRW')
        else:
            df_portfolio['Currency'] = df_portfolio['Currency'].replace("", None)
            df_portfolio['Currency'] = df_portfolio.apply(
                lambda row: 'USD' if str(row['Ticker']).isalpha() else 'KRW' if pd.isna(row['Currency']) else row['Currency'], 
                axis=1
            )
        
    ai_records = doc.worksheet("AI_Reports").get_all_records()
    df_ai = pd.DataFrame(ai_records)
    latest_ai_report = df_ai.iloc[-1] if not df_ai.empty else None
    
    return df_portfolio, latest_ai_report

# --- 대시보드 UI 구성 ---
st.title("🏦 포트폴리오 모니터링 콕핏 (Cockpit)")
st.markdown("---")

try:
    usd_krw = get_usd_krw_rate()
    st.sidebar.markdown(f"### 💵 실시간 고시 환율\n**1 USD = {usd_krw:,.2f} KRW**")

    with st.spinner("실시간 시장 데이터 동기화 중..."):
        df_portfolio, latest_ai_report = load_data()

    if not df_portfolio.empty:
        # 수치형 데이터 전처리
        df_portfolio['Shares'] = pd.to_numeric(df_portfolio['Shares'], errors='coerce').fillna(0)
        df_portfolio['Current_Price'] = pd.to_numeric(df_portfolio['Current_Price'], errors='coerce').fillna(0)
        
        # 💡 [핵심 연산] 통화가 USD 일 경우 환율을 반영하여 원화 총자산 가치 산출
        df_portfolio['Total_Value_KRW'] = df_portfolio.apply(
            lambda r: r['Shares'] * r['Current_Price'] * usd_krw if r['Currency'] == 'USD' else r['Shares'] * r['Current_Price'],
            axis=1
        )
        
        # 계좌 그룹별 원화 환산 자산 연산
        total_asset = df_portfolio['Total_Value_KRW'].sum()
        normal_asset = df_portfolio[df_portfolio['Account'] == '일반']['Total_Value_KRW'].sum()
        pension_asset = df_portfolio[df_portfolio['Account'] == '연금']['Total_Value_KRW'].sum()

        # 메트릭 대형 전광판 배치
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(label="💰 총 평가 자산 (원화 합산)", value=f"{total_asset:,.0f} 원")
        with col2:
            st.metric(label="💵 일반 주식계좌 자산", value=f"{normal_asset:,.0f} 원")
        with col3:
            st.metric(label="🛡️ 연금저축/IRP 자산", value=f"{pension_asset:,.0f} 원")
            
        st.markdown("---")

        # 메인 영역: 계좌 타입별 분류 탭 조율
        st.subheader("📊 자산 보유 현황 및 배분")
        account_tab1, account_tab2, account_tab3 = st.tabs(["전체 보기", "일반 주식계좌", "연금저축/IRP"])
        
        # 보기 편하게 정렬 및 포맷팅용 가공
        display_df = df_portfolio[['Ticker', 'Currency', 'Shares', 'Current_Price', 'Total_Value_KRW', 'Account']].copy()
        
        with account_tab1:
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        with account_tab2:
            st.dataframe(display_df[display_df['Account'] == '일반'], use_container_width=True, hide_index=True)
        with account_tab3:
            st.dataframe(display_df[display_df['Account'] == '연금'], use_container_width=True, hide_index=True)
            
    else:
        st.info("현재 포트폴리오에 등록된 종목이 없습니다. 텔레그램을 통해 등록해 주세요.")

    st.markdown("---")

    # 하단 영역: AI 애널리스트 리포트
    st.subheader("🤖 AI 리포트 브리핑 룸")
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
