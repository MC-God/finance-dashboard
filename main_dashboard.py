import streamlit as st
import pandas as pd
import os
import json
import requests
import plotly.express as px
from datetime import datetime
from dotenv import load_dotenv
from src.sheets_client import get_sheet_client

# --- 페이지 기본 설정 (와이드 모드 적용) ---
st.set_page_config(page_title="Hedge Fund Style Cockpit", page_icon="🏦", layout="wide")

# Custom CSS를 주입하여 표와 UI의 폰트 및 프로페셔널한 금융 다크톤 레이아웃 보완
st.markdown("""
    <style>
    .metric-label { font-size: 14px !important; color: #888888 !important; }
    .stDataFrame div[data-testid="stTable"] { font-size: 13px !important; }
    </style>
""", unsafe_allow_html=True)

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
@st.cache_data(ttl=30)
def load_all_dashboard_data():
    client = get_sheet_client()
    doc = client.open_by_key(SPREADSHEET_ID)
    
    portfolio_records = doc.worksheet("Portfolio").get_all_records()
    df_portfolio = pd.DataFrame(portfolio_records)
    
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

# 유연한 컬럼 검색기
def find_column(df, possible_names):
    if df is None or df.empty:
        return None
    for name in possible_names:
        for col in df.columns:
            if str(col).strip().lower() == name.lower():
                return col
    return None

# --- 대시보드 메인 콕핏 렌더링 ---
st.title("🏦 포트폴리오 자산 운용 콕핏")

try:
    usd_krw = get_usd_krw_rate()
    st.caption(f"📡 실시간 고시 환율 기준: 1 USD = {usd_krw:,.2f} KRW")

    with st.spinner("인프라 데이터 동기화 중..."):
        df_portfolio, df_history, latest_ai_report = load_all_dashboard_data()

    # --- 💡 1. 전일 대비 증감 연산 로직 전면 재개편 ---
    def get_delta_fixed(df_h, account_filter=None):
        if df_h is None or df_h.empty: 
            return 0, 0
            
        val_col = find_column(df_h, ['total_value_krw', 'value', '평가가치'])
        date_col = find_column(df_h, ['date', '날짜', '일자'])
        acc_col_h = find_column(df_h, ['account', '계좌', '계좌구분'])
        
        if not val_col or not date_col or not acc_col_h:
            return 0, 0
            
        try:
            df_h_clean = df_h.copy()
            # 날짜 포맷 표준화 문자열 변환 후 유일 날짜 소팅
            df_h_clean[date_col] = df_h_clean[date_col].astype(str).str.strip()
            unique_dates = sorted(df_h_clean[date_col].unique())
            
            if len(unique_dates) < 2: 
                return 0, 0
                
            latest_date = unique_dates[-1]
            prev_date = unique_dates[-2]
            
            def sum_val_for_date(target_date):
                target_df = df_h_clean[df_h_clean[date_col] == target_date]
                if account_filter:
                    target_df = target_df[target_df[acc_col_h].astype(str).str.strip() == account_filter]
                return pd.to_numeric(target_df[val_col], errors='coerce').sum()
                
            curr_sum = sum_val_for_date(latest_date)
            prev_sum = sum_val_for_date(prev_date)
            
            diff = curr_sum - prev_sum
            pct = (diff / prev_sum * 100) if prev_sum != 0 else 0
            return diff, pct
        except Exception:
            return 0, 0

    # 기본 컬럼 매핑 추적
    ticker_col = find_column(df_portfolio, ['ticker', '종목', '종목코드'])
    shares_col = find_column(df_portfolio, ['shares', '수량', '보유수량'])
    price_col = find_column(df_portfolio, ['current_price', '현재가', '가격'])
    avg_col = find_column(df_portfolio, ['avg_price', '평단가', '매입단가'])
    curr_col = find_column(df_portfolio, ['currency', '통화'])
    acc_col = find_column(df_portfolio, ['account', '계좌', '계좌구분'])
    name_col = find_column(df_portfolio, ['stock_name', '종목명', '회사명'])
    return_col = find_column(df_portfolio, ['1d_return', '등락률', '변동률'])

    total_asset, normal_asset, pension_asset = 0, 0, 0
    total_diff, total_pct = get_delta_fixed(df_history)
    normal_diff, normal_pct = get_delta_fixed(df_history, "일반")
    pension_diff, pension_pct = get_delta_fixed(df_history, "연금")

    if not df_portfolio.empty and ticker_col and shares_col and price_col:
        df_portfolio[shares_col] = pd.to_numeric(df_portfolio[shares_col], errors='coerce').fillna(0)
        df_portfolio[price_col] = pd.to_numeric(df_portfolio[price_col], errors='coerce').fillna(0)
        df_portfolio[avg_col] = pd.to_numeric(df_portfolio[avg_col], errors='coerce').fillna(0)
        
        if not curr_col: df_portfolio['Currency'] = df_portfolio[ticker_col].apply(lambda x: 'USD' if str(x).isalpha() else 'KRW')
        if not acc_col: df_portfolio['Account'] = '일반'

        df_portfolio['Total_Value_KRW'] = df_portfolio.apply(
            lambda r: r[shares_col] * r[price_col] * usd_krw if str(r[find_column(df_portfolio, ['currency', 'Currency'])]).upper() == 'USD' else r[shares_col] * r[price_col],
            axis=1
        )
        
        # 💡 2. 자산 테이블 가시성을 극대화하기 위한 개별 수익률(ROI) 연산 추가
        df_portfolio['Total_Cost_KRW'] = df_portfolio.apply(
            lambda r: r[shares_col] * r[avg_col] * usd_krw if str(r[find_column(df_portfolio, ['currency', 'Currency'])]).upper() == 'USD' else r[shares_col] * r[avg_col],
            axis=1
        )
        df_portfolio['수익률'] = df_portfolio.apply(
            lambda r: ((r['Total_Value_KRW'] - r['Total_Cost_KRW']) / r['Total_Cost_KRW'] * 100) if r['Total_Cost_KRW'] != 0 else 0.0,
            axis=1
        )
        
        total_asset = df_portfolio['Total_Value_KRW'].sum()
        normal_asset = df_portfolio[df_portfolio[find_column(df_portfolio, ['account', 'Account'])] == '일반']['Total_Value_KRW'].sum()
        pension_asset = df_portfolio[df_portfolio[find_column(df_portfolio, ['account', 'Account'])] == '연금']['Total_Value_KRW'].sum()

    # ==========================================
    # 💰 PART 1: High-End KPI 전광판 메트릭 (교정 완료)
    # ==========================================
    m1, m2, m3 = st.columns(3)
    m1.metric("💰 총 자산 합계", f"{total_asset:,.0f} 원", f"{total_diff:+,.0f} 원 ({total_pct:+.2f}%)", delta_color="inverse")
    m2.metric("💵 일반 주식계좌 자산", f"{normal_asset:,.0f} 원", f"{normal_diff:+,.0f} 원 ({normal_pct:+.2f}%)", delta_color="inverse")
    m3.metric("🛡️ 연금저축/IRP 자산", f"{pension_asset:,.0f} 원", f"{pension_diff:+,.0f} 원 ({pension_pct:+.2f}%)", delta_color="inverse")

    st.markdown("---")

    # ==========================================
    # 📈 PART 2: 하이엔드 시각화 레이아웃 (타임라인 + 비중)
    # ==========================================
    g1, g2 = st.columns([6, 4])
    
    with g1:
        st.subheader("📈 자산 성장 타임라인")
        val_col_hist = find_column(df_history, ['total_value_krw', 'value', '평가가치'])
        date_col_hist = find_column(df_history, ['date', '날짜', '일자'])
        acc_col_hist = find_column(df_history, ['account', '계좌', '계좌구분'])
        
        if not df_history.empty and val_col_hist and date_col_hist and acc_col_hist:
            df_history[date_col_hist] = pd.to_datetime(df_history[date_col_hist])
            df_timeline = df_history.groupby([date_col_hist, acc_col_hist])[val_col_hist].sum().unstack(fill_value=0)
            df_timeline['Total'] = df_timeline.sum(axis=1)
            st.line_chart(df_timeline)
        else:
            st.info("📅 아직 데이터 축적량이 부족합니다. 내일 밤 정산 스크립트 실행 후 타임라인 곡선이 형성됩니다.")

    with g2:
        st.subheader("🍕 포트폴리오 자산 배분 비중")
        if not df_portfolio.empty and ticker_col:
            def categorize(row):
                name = str(row.get(name_col, '')) if name_col else ''
                ticker = str(row.get(ticker_col, '')).upper()
                currency_val = str(row.get(find_column(df_portfolio, ['currency', 'Currency']), 'KRW')).upper()
                
                if '금' in name or ticker in ['IAU', 'GLD', '411060', '132030']:
                    return "금 (Gold) ETF"
                elif currency_val == "USD":
                    return "미국 주식 (USD)"
                else:
                    return "한국 주식 (KRW)"
            
            df_portfolio['Category'] = df_portfolio.apply(categorize, axis=1)
            pie_data = df_portfolio.groupby('Category')['Total_Value_KRW'].sum().reset_index()
            
            fig = px.pie(pie_data, values='Total_Value_KRW', names='Category', hole=0.4,
                         color_discrete_sequence=['#FF4B4B', '#1C83E1', '#FBC02D'])
            fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), showlegend=True)
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # ==========================================
    # 📊 PART 3: 💡 자산 세부 보유 현황 테이블 고도화 개편
    # ==========================================
    st.subheader("📊 핵심 포트폴리오 스냅샷 (수익률 순 정렬)")
    if not df_portfolio.empty:
        # 가시성을 지극히 높이기 위한 전용 포맷터 전처리 데이터프레임 가공
        df_display = pd.DataFrame()
        df_display['종목코드'] = df_portfolio[ticker_col]
        df_display['종목명'] = df_portfolio[name_col].fillna(df_portfolio[ticker_col])
        df_display['보유수량'] = df_portfolio[shares_col].apply(lambda x: f"{int(x):,}" if x.is_integer() else f"{x:,.2f}")
        
        # 통화별 단위 매핑
        df_display['매수가'] = df_portfolio.apply(lambda r: f"${r[avg_col]:,.2f}" if str(r[find_column(df_portfolio, ['currency', 'Currency'])]).upper() == 'USD' else f"{int(r[avg_col]):,}원", axis=1)
        df_display['현재가'] = df_portfolio.apply(lambda r: f"${r[price_col]:,.2f}" if str(r[find_column(df_portfolio, ['currency', 'Currency'])]).upper() == 'USD' else f"{int(r[price_col]):,}원", axis=1)
        
        # 수익률 수치 저장 및 포맷팅 (정렬용)
        df_display['_raw_roi'] = df_portfolio['수익률']
        df_display['수익률'] = df_portfolio['수익률'].apply(lambda x: f"🔴 {x:+.2f}%" if x > 0 else f"🔵 {x:+.2f}%" if x < 0 else f"⚪ {x:.2f}%")
        df_display['평가가치(원화)'] = df_portfolio['Total_Value_KRW'].apply(lambda x: f"{int(x):,} 원")
        df_display['계좌'] = df_portfolio[find_column(df_portfolio, ['account', 'Account'])]
        
        # 💡 핵심 요청사항: 수익률(내림차순)로 데이터 정렬 및 인덱스 숨김
        df_display = df_display.sort_values(by='_raw_roi', ascending=False).drop(columns=['_raw_roi'])
        
        account_tab1, account_tab2, account_tab3 = st.tabs(["전체 자산 현황", "일반 주식 자산", "연금저축/IRP 자산"])
        with account_tab1:
            st.dataframe(df_display, use_container_width=True, hide_index=True)
        with account_tab2:
            st.dataframe(df_display[df_display['계좌'] == '일반'], use_container_width=True, hide_index=True)
        with account_tab3:
            st.dataframe(df_display[df_display['계좌'] == '연금'], use_container_width=True, hide_index=True)
    else:
        st.info("조회할 세부 장부가 비어 있습니다.")

    # ==========================================
    # 🤖 PART 4: 💡 AI 리포트 브리핑 룸 포맷 일치화 개편
    # ==========================================
    st.markdown("---")
    st.subheader("🤖 AI 리포트 브리핑 룸 (Hedge Fund Layout)")
    if latest_ai_report is not None:
        st.caption(f"📅 리포트 릴리즈 시점: {latest_ai_report.get('Date', 'N/A')}")
        
        tab1, tab2, tab3, tab4 = st.tabs(["📉 퀀트 (Quant)", "🌍 매크로 (Macro)", "💎 가치투자 (Value)", "🚀 텐베거 (10-Bagger)"])
        
        # 💡 깔끔하고 일관성 있는 금융 리포트 마크다운 구조로 일치화 렌더링
        def render_opinion(title, content):
            st.markdown(f"### 📋 {title} 심층 분석")
            st.markdown(f"> **Executive Summary:** 본 리포트는 구글 시트 거래 원장 및 마스터 팩터를 연동하여 산출된 결과입니다.")
            st.markdown("---")
            st.markdown(content)
            st.markdown("---")
            st.caption("⚠️ 본 분석은 투자 보조 인프라 데이터이며, 최종 투자 책임은 본인에게 있습니다.")

        with tab1: render_opinion("퀀트 포지셔닝 의견", latest_ai_report.get('Quant_Opinion', '데이터 없음'))
        with tab2: render_opinion("글ローバル 매크로 의견", latest_ai_report.get('Macro_Opinion', '데이터 없음'))
        with tab3: render_opinion("밸류에이션 가치투자 의견", latest_ai_report.get('Value_Opinion', '데이터 없음'))
        with tab4: render_opinion("혁신성장 텐베거 탐색 의견", latest_ai_report.get('Ten_Bagger_Opinion', '데이터 없음'))

except Exception as e:
    st.error("대시보드 엔진 구동 중 예외가 발생했습니다.")
    st.exception(e)
