import streamlit as st
import pandas as pd
import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
from src.sheets_client import get_sheet_client

# --- 페이지 기본 설정 (와이드 모드로 프로페셔널함 극대화) ---
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

# --- 환율 가져오기 함수 ---
def get_usd_krw_rate():
    try:
        res = requests.get("https://open.er-api.com/v6/latest/USD", timeout=3)
        if res.status_code == 200:
            return float(res.json()["rates"]["KRW"])
    except Exception:
        pass
    return 1350.0

# --- 데이터 통합 로드 함수 ---
@st.cache_data(ttl=60)
def load_all_dashboard_data():
    client = get_sheet_client()
    doc = client.open_by_key(SPREADSHEET_ID)
    
    # 1. 포트폴리오 스냅샷 읽기
    portfolio_records = doc.worksheet("Portfolio").get_all_records()
    df_portfolio = pd.DataFrame(portfolio_records)
    
    # 2. 시계열 역사 기록 읽기
    df_history = pd.DataFrame()
    try:
        history_records = doc.worksheet("History").get_all_records()
        df_history = pd.DataFrame(history_records)
    except Exception:
        pass
        
    ai_records = doc.worksheet("AI_Reports").get_all_records()
    df_ai = pd.DataFrame(ai_records)
    latest_ai_report = df_ai.iloc[-1] if not df_ai.empty else None
    
    return df_portfolio, df_history, latest_ai_report

# 💡 대소문자 및 공백 오차로 인한 KeyError를 원천 차단하는 정밀 컬럼 검색 추적기
def find_column(df, possible_names):
    for name in possible_names:
        for col in df.columns:
            if str(col).strip().lower() == name.lower():
                return col
    return None

# --- 대시보드 메인 콕핏 렌더링 ---
st.title("🏦 포트폴리오 자산 운용 콕핏 (Cockpit)")
st.markdown("---")

try:
    usd_krw = get_usd_krw_rate()
    st.sidebar.markdown(f"### 💵 고시 환율 기동 정보\n**1 USD = {usd_krw:,.2f} KRW**")

    with st.spinner("인프라 스트림 데이터 동기화 중..."):
        df_portfolio, df_history, latest_ai_report = load_all_dashboard_data()

    # ==========================================
    # 📈 PART 1: 자산 성장 타임라인 트랙 (안전 필터 강화)
    # ==========================================
    st.subheader("📈 자산 성장 타임라인 (Portfolio Wealth Timeline)")
    
    val_col_hist = find_column(df_history, ['total_value_krw', 'value', '평가가치'])
    date_col_hist = find_column(df_history, ['date', '날짜', '일자'])
    acc_col_hist = find_column(df_history, ['account', '계좌', '계좌구분'])

    if not df_history.empty and val_col_hist and date_col_hist and acc_col_hist:
        try:
            df_history[val_col_hist] = pd.to_numeric(df_history[val_col_hist], errors='coerce').fillna(0)
            
            df_timeline = df_history.groupby([date_col_hist, acc_col_hist])[val_col_hist].sum().unstack(fill_value=0).reset_index()
            df_timeline[date_col_hist] = pd.to_datetime(df_timeline[date_col_hist])
            df_timeline = df_timeline.sort_values(date_col_hist).set_index(date_col_hist)
            
            df_timeline = df_timeline.rename(columns={c: str(c) for c in df_timeline.columns})
            df_timeline['총 자산 총액'] = df_timeline.sum(axis=1)
            
            chart_cols = ['총 자산 총액'] + [c for c in ['일반', '연금'] if c in df_timeline.columns]
            st.line_chart(df_timeline[chart_cols], use_container_width=True)
        except Exception as timeline_err:
            st.warning(f"📊 시계열 데이터를 변환하는 중입니다. 잠시만 기다려주세요... (상세: {timeline_err})")
    else:
        st.info("📅 아직 축적된 자산 시계열 히스토리 데이터가 충분하지 않습니다. 매일 밤 19시 정산 자동화 스크립트가 실행되면서 타임라인 곡선이 형성됩니다.")
        
    st.markdown("---")

    # ==========================================
    # 📊 PART 2: 실시간 KPI 전광판 및 테이블 자산 영역
    # ==========================================
    ticker_col = find_column(df_portfolio, ['ticker', '종목', '종목코드'])
    shares_col = find_column(df_portfolio, ['shares', '수량', '보유수량'])
    price_col = find_column(df_portfolio, ['current_price', '현재가', '가격'])
    curr_col = find_column(df_portfolio, ['currency', '통화'])
    acc_col = find_column(df_portfolio, ['account', '계좌'])
    name_col = find_column(df_portfolio, ['stock_name', '종목명', '회사명'])
    return_col = find_column(df_portfolio, ['1d_return', '등락률', '변동률'])
    avg_col = find_column(df_portfolio, ['avg_price', '평단가', '매입단가'])

    if not df_portfolio.empty and ticker_col and shares_col and price_col:
        df_portfolio[shares_col] = pd.to_numeric(df_portfolio[shares_col], errors='coerce').fillna(0)
        df_portfolio[price_col] = pd.to_numeric(df_portfolio[price_col], errors='coerce').fillna(0)
        
        if not curr_col:
            df_portfolio['Currency'] = df_portfolio[ticker_col].apply(lambda x: 'USD' if str(x).isalpha() else 'KRW')
            curr_col = 'Currency'
            
        if not acc_col:
            df_portfolio['Account'] = '일반'
            acc_col = 'Account'

        df_portfolio['Total_Value_KRW'] = df_portfolio.apply(
            lambda r: r[shares_col] * r[price_col] * usd_krw if str(r[curr_col]).upper() == 'USD' else r[shares_col] * r[price_col],
            axis=1
        )
        
        total_asset = df_portfolio['Total_Value_KRW'].sum()
        normal_asset = df_portfolio[df_portfolio[acc_col] == '일반']['Total_Value_KRW'].sum()
        pension_asset = df_portfolio[df_portfolio[acc_col] == '연금']['Total_Value_KRW'].sum()

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(label="💰 총 평가 자산 (원화 환산 합계)", value=f"{total_asset:,.0f} 원")
        with col2:
            st.metric(label="💵 일반 주식계좌 자산", value=f"{normal_asset:,.0f} 원")
        with col3:
            st.metric(label="🛡️ 연금저축/IRP 자산", value=f"{pension_asset:,.0f} 원")
            
        st.markdown("---")

        st.subheader("📊 자산 세부 보유 현황")
        account_tab1, account_tab2, account_tab3 = st.tabs(["전체 보유 종목", "일반 계좌 포트", "연금 혜택 포트"])
        
        display_cols = [c for c in [ticker_col, name_col, curr_col, shares_col, avg_col, price_col, 'Total_Value_KRW', return_col, acc_col] if c]
        display_df = df_portfolio[display_cols].copy()
        
        with account_tab1:
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        with account_tab2:
            st.dataframe(display_df[display_df[acc_col] == '일반'], use_container_width=True, hide_index=True)
        with account_tab3:
            st.dataframe(display_df[display_df[acc_col] == '연금'], use_container_width=True, hide_index=True)
            
    else:
        st.info("현재 포트폴리오에 등록된 종목이 없거나 동기화 중입니다. 텔레그램을 통해 등록해 주세요.")

    st.markdown("---")

    # ==========================================
    # 👑 PART 3: AI 애널리스트 리포트 브리핑 룸
    # ==========================================
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
    st.error(f"데이터 렌더링 중 대시보드 시스템 예외 발생: {e}")
