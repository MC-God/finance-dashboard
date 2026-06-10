import streamlit as st
import pandas as pd
import os
import json
import requests
import plotly.express as px
from dotenv import load_dotenv
from src.sheets_client import get_sheet_client

# --- 1. 대시보드 기본 설정 ---
st.set_page_config(page_title="Hedge Fund Style Cockpit", page_icon="🏦", layout="wide")

st.markdown("""
    <style>
    .report-box { background-color: #1a1c23; padding: 20px; border-radius: 8px; border-left: 5px solid #FF4B4B; margin-bottom: 15px; }
    </style>
""", unsafe_allow_html=True)

if "google_credentials" in st.secrets:
    try:
        creds_dict = dict(st.secrets["google_credentials"])
        with open("credentials.json", "w", encoding="utf-8") as f:
            json.dump(creds_dict, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"인증서 세팅 오류: {e}")

load_dotenv()
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID") or st.secrets.get("SPREADSHEET_ID")

def get_usd_krw_rate():
    try:
        res = requests.get("https://open.er-api.com/v6/latest/USD", timeout=3)
        if res.status_code == 200: return float(res.json()["rates"]["KRW"])
    except Exception: pass
    return 1350.0

# --- 2. 직관적이고 깔끔한 데이터 로드 ---
@st.cache_data(ttl=30)
def load_data():
    client = get_sheet_client()
    doc = client.open_by_key(SPREADSHEET_ID)
    
    # get_all_records()는 첫 행을 헤더로 삼아 깔끔한 딕셔너리 리스트를 반환합니다.
    df_port = pd.DataFrame(doc.worksheet("Portfolio").get_all_records())
    
    try:
        df_hist = pd.DataFrame(doc.worksheet("History").get_all_records())
    except Exception:
        df_hist = pd.DataFrame()
        
    try:
        ai_records = doc.worksheet("AI_Reports").get_all_records()
        latest_ai = ai_records[-1] if ai_records else None
    except Exception:
        latest_ai = None
        
    return df_port, df_hist, latest_ai

# --- 3. 데이터 전처리 및 핵심 연산 ---
def process_history(df):
    """History 데이터를 연산하기 좋은 순수 숫자/날짜 포맷으로 변환"""
    if df.empty or 'Date' not in df.columns or 'Total_Value_KRW' not in df.columns:
        return pd.DataFrame()
    
    df_clean = df.copy()
    # 날짜 포맷팅
    df_clean['Date'] = pd.to_datetime(df_clean['Date'], errors='coerce').dt.date
    df_clean = df_clean.dropna(subset=['Date'])
    
    # 금액 포맷팅 (콤마 제거 후 숫자로)
    df_clean['Total_Value_KRW'] = pd.to_numeric(df_clean['Total_Value_KRW'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    return df_clean

def calculate_delta(df_hist, account=None):
    """가장 직관적인 Pandas 그룹바이 기반 증감액 연산"""
    if df_hist.empty: return 0, 0
    
    df = df_hist.copy()
    if account and 'Account' in df.columns:
        df = df[df['Account'] == account]
        
    # 날짜별 자산 총합 계산
    daily_sum = df.groupby('Date')['Total_Value_KRW'].sum()
    
    # 비교할 날짜가 2일치 미만이면 0 반환
    if len(daily_sum) < 2: return 0, 0
    
    # 시간순 정렬 후 최신 날짜와 직전 날짜 비교
    sorted_dates = sorted(daily_sum.index)
    latest_val = daily_sum[sorted_dates[-1]]
    prev_val = daily_sum[sorted_dates[-2]]
    
    diff = latest_val - prev_val
    pct = (diff / prev_val * 100) if prev_val != 0 else 0
    return diff, pct

# --- 4. 대시보드 렌더링 ---
st.title("🏦 포트폴리오 자산 운용 콕핏")

try:
    usd_krw = get_usd_krw_rate()
    st.caption(f"📡 실시간 고시 환율 기준: 1 USD = {usd_krw:,.2f} KRW")

    with st.spinner("데이터 동기화 중..."):
        raw_port, raw_hist, latest_ai_report = load_data()

    # 데이터 전처리 실행
    df_hist = process_history(raw_hist)
    df_port = raw_port.copy()

    # 포트폴리오 연산
    total_asset, normal_asset, pension_asset = 0, 0, 0
    total_diff, total_pct = calculate_delta(df_hist)
    normal_diff, normal_pct = calculate_delta(df_hist, "일반")
    pension_diff, pension_pct = calculate_delta(df_hist, "연금")

    if not df_port.empty:
        # 안전한 숫자 변환
        for col in ['Shares', 'Current_Price', 'Avg_Price']:
            if col in df_port.columns:
                df_port[col] = pd.to_numeric(df_port[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
                
        # 평가액 및 수익률 연산
        df_port['Total_Value_KRW'] = df_port.apply(lambda r: r['Shares'] * r['Current_Price'] * (usd_krw if str(r.get('Currency', '')).upper() == 'USD' else 1), axis=1)
        df_port['Total_Cost_KRW'] = df_port.apply(lambda r: r['Shares'] * r['Avg_Price'] * (usd_krw if str(r.get('Currency', '')).upper() == 'USD' else 1), axis=1)
        
        df_port['ROI'] = df_port.apply(lambda r: ((r['Total_Value_KRW'] - r['Total_Cost_KRW']) / r['Total_Cost_KRW'] * 100) if r['Total_Cost_KRW'] != 0 else 0, axis=1)
        
        total_asset = df_port['Total_Value_KRW'].sum()
        if 'Account' in df_port.columns:
            normal_asset = df_port[df_port['Account'] == '일반']['Total_Value_KRW'].sum()
            pension_asset = df_port[df_port['Account'] == '연금']['Total_Value_KRW'].sum()

    # --- PART 1: 커스텀 HTML KPI 전광판 ---
    def render_metric_card(title, value, diff, pct):
        color, arrow, sign = ("#FF4B4B", "🔺", "+") if diff > 0 else ("#1C83E1", "🔻", "") if diff < 0 else ("#888888", "▫️", "+")
        return f"""
        <div style="background-color: #1e222b; padding: 20px; border-radius: 8px; border: 1px solid #2e3440;">
            <p style="color: #b0b5c0; font-size: 15px; margin-bottom: 5px; font-weight: 600;">{title}</p>
            <h2 style="color: white; margin: 0; font-size: 32px; letter-spacing: -0.5px;">{value:,.0f} <span style="font-size:16px; font-weight:normal; color:#888;">원</span></h2>
            <p style="color: {color}; margin-top: 8px; font-size: 15px; margin-bottom: 0; font-weight: 500;">{arrow} {sign}{diff:,.0f} 원 ({sign}{pct:.2f}%)</p>
        </div>
        """

    m1, m2, m3 = st.columns(3)
    with m1: st.markdown(render_metric_card("💰 총 자산 합계", total_asset, total_diff, total_pct), unsafe_allow_html=True)
    with m2: st.markdown(render_metric_card("💵 일반 주식계좌 자산", normal_asset, normal_diff, normal_pct), unsafe_allow_html=True)
    with m3: st.markdown(render_metric_card("🛡️ 연금저축/IRP 자산", pension_asset, pension_diff, pension_pct), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # --- PART 2: 자산 시계열 및 비중 차트 ---
    g1, g2 = st.columns([6, 4])
    
    with g1:
        st.subheader("📈 자산 성장 타임라인")
        if not df_hist.empty:
            df_timeline = df_hist.groupby(['Date', 'Account'])['Total_Value_KRW'].sum().unstack(fill_value=0)
            df_timeline['총자산'] = df_timeline.sum(axis=1)
            st.line_chart(df_timeline)
        else:
            st.info("📅 아직 데이터 축적량이 부족합니다.")

    with g2:
        st.subheader("🍕 포트폴리오 자산 배분 비중")
        if not df_port.empty:
            def categorize(row):
                name, ticker = str(row.get('Stock_Name', '')), str(row.get('Ticker', '')).upper()
                if '금' in name or ticker in ['IAU', 'GLD', '411060', '132030']: return "금 (Gold) ETF"
                elif str(row.get('Currency', '')).upper() == "USD": return "미국 주식 (USD)"
                return "한국 주식 (KRW)"
            
            df_port['Category'] = df_port.apply(categorize, axis=1)
            pie_data = df_port.groupby('Category')['Total_Value_KRW'].sum().reset_index()
            fig = px.pie(pie_data, values='Total_Value_KRW', names='Category', hole=0.4, color_discrete_sequence=['#FF4B4B', '#1C83E1', '#FBC02D'])
            fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), showlegend=True, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # --- PART 3: 자산 세부 보유 현황 테이블 ---
    st.subheader("📊 핵심 포트폴리오 스냅샷 (수익률 순 정렬)")
    if not df_port.empty:
        df_display = pd.DataFrame()
        df_display['종목명'] = df_port['Stock_Name']
        df_display['보유수량'] = df_port['Shares'].apply(lambda x: f"{int(x):,}" if float(x).is_integer() else f"{x:,.2f}")
        df_display['매수가'] = df_port.apply(lambda r: f"${r['Avg_Price']:,.2f}" if str(r.get('Currency')).upper() == 'USD' else f"{int(r['Avg_Price']):,}원", axis=1)
        df_display['현재가'] = df_port.apply(lambda r: f"${r['Current_Price']:,.2f}" if str(r.get('Currency')).upper() == 'USD' else f"{int(r['Current_Price']):,}원", axis=1)
        
        df_display['ROI_Val'] = df_port['ROI']
        df_display['수익률'] = df_port['ROI'].apply(lambda x: f"🔺 {x:+.2f}%" if x > 0 else f"🔻 {x:+.2f}%" if x < 0 else f"▫️ {x:.2f}%")
        df_display['평가가치'] = df_port['Total_Value_KRW'].apply(lambda x: f"{int(x):,} 원")
        df_display['계좌'] = df_port['Account']
        
        df_display = df_display.sort_values(by='ROI_Val', ascending=False).drop(columns=['ROI_Val'])
        
        tab1, tab2, tab3 = st.tabs(["전체", "일반", "연금"])
        with tab1: st.dataframe(df_display, use_container_width=True, hide_index=True)
        with tab2: st.dataframe(df_display[df_display['계좌'] == '일반'], use_container_width=True, hide_index=True)
        with tab3: st.dataframe(df_display[df_display['계좌'] == '연금'], use_container_width=True, hide_index=True)
    else:
        st.info("조회할 내역이 없습니다.")

    # --- PART 4: AI 리포트 ---
    st.markdown("---")
    st.subheader("🤖 AI 리포트 브리핑 룸")
    if latest_ai_report:
        st.caption(f"📅 리포트 공시 시점: {latest_ai_report.get('Date', 'N/A')}")
        tabs = st.tabs(["📉 퀀트", "🌍 매크로", "💎 가치투자", "🚀 텐베거"])
        sections = [("시스템 퀀트 분석", 'Quant_Opinion'), ("글로벌 매크로 환경", 'Macro_Opinion'), ("가치투자 분석", 'Value_Opinion'), ("텐베거 탐색", 'Ten_Bagger_Opinion')]
        
        for tab, (title, key) in zip(tabs, sections):
            with tab:
                st.markdown(f"### 📋 {title}")
                st.markdown(f"<div class='report-box'>{latest_ai_report.get(key, '데이터 없음')}</div>", unsafe_allow_html=True)

except Exception as e:
    st.error(f"대시보드 구동 중 오류: {e}")
