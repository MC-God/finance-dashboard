import streamlit as st
import pandas as pd
import os
import json
import requests
import plotly.express as px # 💡 비중 시각화를 위한 라이브러리 추가
from datetime import datetime, timedelta
from dotenv import load_dotenv
from src.sheets_client import get_sheet_client

# --- 페이지 기본 설정 ---
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
    for name in possible_names:
        for col in df.columns:
            if str(col).strip().lower() == name.lower():
                return col
    return None

# --- 대시보드 UI 구성 ---
st.title("🏦 포트폴리오 자산 운용 콕핏")

try:
    usd_krw = get_usd_krw_rate()
    # 💡 1. 고시환율을 제목 밑에 작은 캡션으로 변경
    st.caption(f"📡 실시간 고시 환율 기준: 1 USD = {usd_krw:,.2f} KRW")

    with st.spinner("인프라 데이터 동기화 중..."):
        df_portfolio, df_history, latest_ai_report = load_all_dashboard_data()

    # --- 데이터 전처리 ---
    ticker_col = find_column(df_portfolio, ['ticker', '종목'])
    shares_col = find_column(df_portfolio, ['shares', '수량'])
    price_col = find_column(df_portfolio, ['current_price', '현재가'])
    curr_col = find_column(df_portfolio, ['currency', '통화'])
    acc_col = find_column(df_portfolio, ['account', '계좌'])
    name_col = find_column(df_portfolio, ['stock_name', '종목명'])
    
    if not df_portfolio.empty and ticker_col and shares_col and price_col:
        df_portfolio[shares_col] = pd.to_numeric(df_portfolio[shares_col], errors='coerce').fillna(0)
        df_portfolio[price_col] = pd.to_numeric(df_portfolio[price_col], errors='coerce').fillna(0)
        
        if not curr_col: df_portfolio['Currency'] = df_portfolio[ticker_col].apply(lambda x: 'USD' if str(x).isalpha() else 'KRW')
        if not acc_col: df_portfolio['Account'] = '일반'
        
        df_portfolio['Total_Value_KRW'] = df_portfolio.apply(
            lambda r: r[shares_col] * r[price_col] * usd_krw if str(r[find_column(df_portfolio, ['currency', 'Currency'])]).upper() == 'USD' else r[shares_col] * r[price_col],
            axis=1
        )

        # ==========================================
        # 💰 PART 1: KPI 메트릭 (전일 대비 증감액 추가)
        # ==========================================
        # 💡 3. 전일 대비 증감 로직 계산
        def get_delta(df_h, account_filter=None):
            if df_h.empty: return 0, 0
            val_col = find_column(df_h, ['total_value_krw', 'value'])
            date_col = find_column(df_h, ['date', '날짜'])
            acc_col_h = find_column(df_h, ['account', '계좌'])
            
            # 날짜순 정렬
            df_h[date_col] = pd.to_datetime(df_h[date_col])
            unique_dates = sorted(df_h[date_col].unique())
            
            if len(unique_dates) < 2: return 0, 0
            
            latest_date = unique_dates[-1]
            prev_date = unique_dates[-2]
            
            def sum_val(target_date):
                target_df = df_h[df_h[date_col] == target_date]
                if account_filter:
                    target_df = target_df[target_df[acc_col_h] == account_filter]
                return target_df[val_col].sum()
            
            curr_sum = sum_val(latest_date)
            prev_sum = sum_val(prev_date)
            
            diff = curr_sum - prev_sum
            pct = (diff / prev_sum * 100) if prev_sum != 0 else 0
            return diff, pct

        total_diff, total_pct = get_delta(df_history)
        normal_diff, normal_pct = get_delta(df_history, "일반")
        pension_diff, pension_pct = get_delta(df_history, "연금")

        total_asset = df_portfolio['Total_Value_KRW'].sum()
        normal_asset = df_portfolio[df_portfolio[find_column(df_portfolio, ['account', 'Account'])] == '일반']['Total_Value_KRW'].sum()
        pension_asset = df_portfolio[df_portfolio[find_column(df_portfolio, ['account', 'Account'])] == '연금']['Total_Value_KRW'].sum()

        m1, m2, m3 = st.columns(3)
        # 💡 한국식 컬러 (상승 빨강, 하락 파랑) 적용을 위해 delta_color="inverse" 사용
        m1.metric("💰 총 자산 합계", f"{total_asset:,.0f} 원", f"{total_diff:+,.0f} 원 ({total_pct:+.2f}%)", delta_color="inverse")
        m2.metric("💵 일반 계좌 자산", f"{normal_asset:,.0f} 원", f"{normal_diff:+,.0f} 원 ({normal_pct:+.2f}%)", delta_color="inverse")
        m3.metric("🛡️ 연금 계좌 자산", f"{pension_asset:,.0f} 원", f"{pension_diff:+,.0f} 원 ({pension_pct:+.2f}%)", delta_color="inverse")

        st.markdown("---")

        # ==========================================
        # 📈 PART 2: 그래프 영역 (타임라인 + 파이차트)
        # ==========================================
        g1, g2 = st.columns([6, 4])
        
        with g1:
            st.subheader("📈 자산 성장 타임라인")
            val_col_hist = find_column(df_history, ['total_value_krw', 'value'])
            date_col_hist = find_column(df_history, ['date', '날짜'])
            acc_col_hist = find_column(df_history, ['account', '계좌'])
            
            if not df_history.empty and val_col_hist:
                df_history[date_col_hist] = pd.to_datetime(df_history[date_col_hist])
                df_timeline = df_history.groupby([date_col_hist, acc_col_hist])[val_col_hist].sum().unstack(fill_value=0)
                df_timeline['Total'] = df_timeline.sum(axis=1)
                st.line_chart(df_timeline)

        with g2:
            # 💡 2. 포트 배분 파이 그래프 시각화
            st.subheader("🍕 자산 배분 비중")
            
            def categorize(row):
                name = str(row.get(name_col, '')).lower()
                ticker = str(row.get(ticker_col, '')).upper()
                # 금 ETF 판별 (종목명에 '금'이 들어가거나 금 관련 티커)
                if '금' in name or ticker in ['IAU', 'GLD', '411060', '132030']:
                    return "금 (Gold) ETF"
                # 미국 주식 판별
                elif str(row.get(find_column(df_portfolio, ['currency', 'Currency']), '')).upper() == "USD":
                    return "미국 주식 (USD)"
                # 그 외 한국 주식
                else:
                    return "한국 주식 (KRW)"
            
            df_portfolio['Category'] = df_portfolio.apply(categorize, axis=1)
            pie_data = df_portfolio.groupby('Category')['Total_Value_KRW'].sum().reset_index()
            
            fig = px.pie(pie_data, values='Total_Value_KRW', names='Category', 
                         hole=0.4, # 도넛 차트 형태
                         color_discrete_sequence=['#FF4B4B', '#1C83E1', '#FBC02D']) # 빨강, 파랑, 노랑(금)
            fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), showlegend=True)
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")

        # ==========================================
        # 📊 PART 3: 세부 보유 현황 테이블
        # ==========================================
        st.subheader("📊 자산 세부 보유 현황")
        display_df = df_portfolio.copy()
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    else:
        st.info("현재 포트폴리오에 등록된 종목이 없습니다. 텔레그램을 통해 등록해 주세요.")

    # ==========================================
    # 🤖 PART 4: AI 리포트
    # ==========================================
    st.markdown("---")
    st.subheader("🤖 AI 리포트 브리핑 룸")
    if latest_ai_report is not None:
        st.caption(f"📅 릴리즈 일자: {latest_ai_report.get('Date', 'N/A')}")
        tab1, tab2, tab3, tab4 = st.tabs(["📉 퀀트", "🌍 매크로", "💎 가치투자", "🚀 텐베거"])
        with tab1: st.markdown(latest_ai_report.get('Quant_Opinion', '데이터 없음'))
        with tab2: st.markdown(latest_ai_report.get('Macro_Opinion', '데이터 없음'))
        with tab3: st.markdown(latest_ai_report.get('Value_Opinion', '데이터 없음'))
        with tab4: st.markdown(latest_ai_report.get('Ten_Bagger_Opinion', '데이터 없음'))

except Exception as e:
    st.error(f"대시보드 렌더링 중 오류 발생: {e}")
