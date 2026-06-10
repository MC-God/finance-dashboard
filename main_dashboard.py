import streamlit as st
import pandas as pd
import os
import json
import requests
import datetime
import plotly.express as px
import pandas_datareader.data as web
from dotenv import load_dotenv
from src.sheets_client import get_sheet_client

# ==========================================
# 1. 초기 설정 및 UI 스타일링
# ==========================================
st.set_page_config(page_title="Hedge Fund Style Cockpit", page_icon="🏦", layout="wide")

st.markdown("""
    <style>
    .metric-card { background-color: #1e222b; padding: 20px; border-radius: 8px; border: 1px solid #2e3440; }
    .metric-title { color: #b0b5c0; font-size: 15px; margin-bottom: 5px; font-weight: 600; }
    .metric-value { color: white; margin: 0; font-size: 32px; letter-spacing: -0.5px; }
    .metric-unit { font-size: 16px; font-weight: normal; color: #888; }
    .report-box { background-color: #1a1c23; padding: 20px; border-radius: 8px; border-left: 5px solid #FF4B4B; margin-bottom: 15px; }
    </style>
""", unsafe_allow_html=True)

# 환경변수 로드
if "google_credentials" in st.secrets:
    try:
        with open("credentials.json", "w", encoding="utf-8") as f:
            json.dump(dict(st.secrets["google_credentials"]), f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"인증서 설정 오류: {e}")

load_dotenv()
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID") or st.secrets.get("SPREADSHEET_ID")

def get_usd_krw_rate():
    try:
        res = requests.get("https://open.er-api.com/v6/latest/USD", timeout=3)
        if res.status_code == 200: return float(res.json()["rates"]["KRW"])
    except: 
        pass
    return 1350.0

# ==========================================
# 2. 데이터 로드 
# ==========================================
@st.cache_data(ttl=30)
def load_data():
    client = get_sheet_client()
    doc = client.open_by_key(SPREADSHEET_ID)
    
    def fetch_sheet(name):
        try:
            worksheet = doc.worksheet(name)
            vals = worksheet.get_all_values()
            if not vals:
                return pd.DataFrame()
            df = pd.DataFrame(vals[1:], columns=vals[0])
            df.columns = df.columns.astype(str).str.strip()
            return df
        except Exception:
            return pd.DataFrame()

    df_port = fetch_sheet("Portfolio")
    df_hist = fetch_sheet("History")
    
    try:
        ai_records = doc.worksheet("AI_Reports").get_all_records()
        latest_ai = ai_records[-1] if ai_records else None
    except:
        latest_ai = None
        
    return df_port, df_hist, latest_ai

# ==========================================
# 3. 데이터 정제 및 연산 엔진
# ==========================================
def clean_numeric(series):
    """문자열에 섞인 콤마, 통화 기호 등을 제거하고 숫자로 강제 변환"""
    cleaned = series.astype(str).str.replace(r'[^\d\.-]', '', regex=True)
    return pd.to_numeric(cleaned, errors='coerce').fillna(0)

def calc_delta(df_hist, account_type=None):
    """History 데이터를 바탕으로 전일 대비 증감액 계산"""
    if df_hist.empty or 'Date' not in df_hist.columns or 'Total_Value_KRW' not in df_hist.columns:
        return 0, 0
        
    df = df_hist.copy()
    
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.normalize()
    df['Total_Value_KRW'] = clean_numeric(df['Total_Value_KRW'])
    df = df.dropna(subset=['Date'])
    
    if account_type and 'Account' in df.columns:
        df = df[df['Account'].str.strip() == account_type]
        
    daily_sum = df.groupby('Date')['Total_Value_KRW'].sum().sort_index()
    
    if len(daily_sum) < 2:
        return 0, 0
        
    latest_val = daily_sum.iloc[-1]
    prev_val = daily_sum.iloc[-2]
    
    diff = latest_val - prev_val
    pct = (diff / prev_val * 100) if prev_val != 0 else 0
    return diff, pct

# ==========================================
# 4. 대시보드 렌더링
# ==========================================
st.title("🏦 포트폴리오 자산 운용 콕핏")

try:
    usd_krw = get_usd_krw_rate()
    st.caption(f"📡 실시간 고시 환율 기준: 1 USD = {usd_krw:,.2f} KRW")

    with st.spinner("데이터 동기화 중..."):
        df_port_raw, df_hist_raw, latest_ai_report = load_data()

    # --- KPI 및 포트폴리오 연산 ---
    total_asset, normal_asset, pension_asset = 0, 0, 0
    total_diff, total_pct = calc_delta(df_hist_raw)
    normal_diff, normal_pct = calc_delta(df_hist_raw, "일반")
    pension_diff, pension_pct = calc_delta(df_hist_raw, "연금")

    df_port = df_port_raw.copy()
    if not df_port.empty:
        df_port['Shares'] = clean_numeric(df_port.get('Shares', pd.Series([0]*len(df_port))))
        df_port['Current_Price'] = clean_numeric(df_port.get('Current_Price', pd.Series([0]*len(df_port))))
        df_port['Avg_Price'] = clean_numeric(df_port.get('Avg_Price', pd.Series([0]*len(df_port))))
        df_port['Currency'] = df_port.get('Currency', pd.Series(['KRW']*len(df_port))).astype(str).str.strip().str.upper()
        df_port['Account'] = df_port.get('Account', pd.Series(['일반']*len(df_port))).astype(str).str.strip()

        def get_krw_val(row, price_col):
            price = row[price_col]
            return price * row['Shares'] * usd_krw if row['Currency'] == 'USD' else price * row['Shares']

        df_port['Total_Value_KRW'] = df_port.apply(lambda r: get_krw_val(r, 'Current_Price'), axis=1)
        df_port['Total_Cost_KRW'] = df_port.apply(lambda r: get_krw_val(r, 'Avg_Price'), axis=1)
        df_port['ROI'] = df_port.apply(lambda r: ((r['Total_Value_KRW'] - r['Total_Cost_KRW']) / r['Total_Cost_KRW'] * 100) if r['Total_Cost_KRW'] > 0 else 0, axis=1)

        total_asset = df_port['Total_Value_KRW'].sum()
        normal_asset = df_port[df_port['Account'] == '일반']['Total_Value_KRW'].sum()
        pension_asset = df_port[df_port['Account'] == '연금']['Total_Value_KRW'].sum()

    # --- 공통 렌더링 함수 (빨강=상승, 파랑=하락 통일) ---
    def render_card(title, value, diff, pct=None, unit="원"):
        if diff > 0:
            color, arrow, sign = "#FF4B4B", "🔺", "+"
        elif diff < 0:
            color, arrow, sign = "#1C83E1", "🔻", ""
        else:
            color, arrow, sign = "#888888", "▫️", ""
            
        value_fmt = f"{value:,.0f}" if unit == "원" else f"{value:.2f}"
        diff_fmt = f"{diff:,.0f} {unit}" if unit == "원" else f"{diff:.2f}%p"
        pct_str = f" ({sign}{pct:.2f}%)" if pct is not None else ""
        
        return f"""
        <div class="metric-card">
            <p class="metric-title">{title}</p>
            <h2 class="metric-value">{value_fmt} <span class="metric-unit">{unit}</span></h2>
            <p style="color: {color}; margin-top: 8px; font-size: 15px; margin-bottom: 0; font-weight: 500;">{arrow} {sign}{diff_fmt}{pct_str}</p>
        </div>
        """

    # --- 매크로 지표 패널 (미국채 2, 10, 30년물) ---
    st.markdown("### 🌍 글로벌 매크로 지표 (실시간)")
    macro_cols = st.columns(3)
    
    @st.cache_data(ttl=3600)
    def fetch_treasury_yields():
        try:
            end = datetime.datetime.now()
            start = end - datetime.timedelta(days=10)
            
            df_2y = web.DataReader('DGS2', 'fred', start, end).dropna()
            df_10y = web.DataReader('DGS10', 'fred', start, end).dropna()
            df_30y = web.DataReader('DGS30', 'fred', start, end).dropna()
            
            def get_vals(df):
                if len(df) >= 2: return df.iloc[-1, 0], df.iloc[-1, 0] - df.iloc[-2, 0]
                elif len(df) == 1: return df.iloc[-1, 0], 0
                return 0, 0
                
            return *get_vals(df_2y), *get_vals(df_10y), *get_vals(df_30y)
        except:
            return 0,0, 0,0, 0,0

    y2_val, y2_diff, y10_val, y10_diff, y30_val, y30_diff = fetch_treasury_yields()

    with macro_cols[0]: st.markdown(render_card("🇺🇸 미 2년물 국채 금리", y2_val, y2_diff, unit="%"), unsafe_allow_html=True)
    with macro_cols[1]: st.markdown(render_card("🇺🇸 미 10년물 국채 금리", y10_val, y10_diff, unit="%"), unsafe_allow_html=True)
    with macro_cols[2]: st.markdown(render_card("🇺🇸 미 30년물 국채 금리", y30_val, y30_diff, unit="%"), unsafe_allow_html=True)
        
    st.markdown("<br>", unsafe_allow_html=True)

    # --- PART 1: 커스텀 HTML 전광판 (자산) ---
    col1, col2, col3 = st.columns(3)
    with col1: st.markdown(render_card("💰 총 자산 합계", total_asset, total_diff, total_pct, "원"), unsafe_allow_html=True)
    with col2: st.markdown(render_card("💵 일반 주식계좌 자산", normal_asset, normal_diff, normal_pct, "원"), unsafe_allow_html=True)
    with col3: st.markdown(render_card("🛡️ 연금저축/IRP 자산", pension_asset, pension_diff, pension_pct, "원"), unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # --- PART 2: 시계열 및 비중 차트 ---
    g1, g2 = st.columns([6, 4])
    
    with g1:
        st.subheader("📈 자산 성장 타임라인")
        if not df_hist_raw.empty and 'Date' in df_hist_raw.columns and 'Total_Value_KRW' in df_hist_raw.columns:
            df_chart = df_hist_raw.copy()
            df_chart['Date'] = pd.to_datetime(df_chart['Date'], errors='coerce').dt.normalize()
            df_chart['Total_Value_KRW'] = clean_numeric(df_chart['Total_Value_KRW'])
            
            if 'Account' not in df_chart.columns:
                df_chart['Account'] = '일반'
            df_chart['Account'] = df_chart['Account'].astype(str).str.strip()
            
            df_chart = df_chart.dropna(subset=['Date'])
            
            if not df_chart.empty:
                df_timeline = df_chart.groupby(['Date', 'Account'])['Total_Value_KRW'].sum().unstack(fill_value=0)
                df_timeline['총 자산'] = df_timeline.sum(axis=1)
                st.line_chart(df_timeline)
            else:
                st.info("차트를 그릴 수 있는 유효한 날짜 데이터가 없습니다.")
        else:
            st.info("📅 아직 데이터 축적량이 부족합니다.")

    with g2:
        st.subheader("🍕 포트폴리오 자산 배분 비중")
        if not df_port.empty:
            def categorize(row):
                name = str(row.get('Stock_Name', ''))
                ticker = str(row.get('Ticker', '')).upper()
                if '금' in name or ticker in ['IAU', 'GLD', '411060', '132030']: return "금 (Gold) ETF"
                elif row['Currency'] == "USD": return "미국 주식 (USD)"
                return "한국 주식 (KRW)"
                
            df_port['Category'] = df_port.apply(categorize, axis=1)
            pie_data = df_port.groupby('Category')['Total_Value_KRW'].sum().reset_index()
            fig = px.pie(pie_data, values='Total_Value_KRW', names='Category', hole=0.4, color_discrete_sequence=['#FF4B4B', '#1C83E1', '#FBC02D'])
            fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), showlegend=True, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # --- PART 3: 자산 세부 보유 현황 ---
    st.subheader("📊 핵심 포트폴리오 스냅샷 (수익률 순 정렬)")
    if not df_port.empty:
        df_display = pd.DataFrame()
        df_display['종목명'] = df_port['Stock_Name']
        df_display['보유수량'] = df_port['Shares'].apply(lambda x: f"{int(x):,}" if float(x).is_integer() else f"{x:,.2f}")
        df_display['매수가'] = df_port.apply(lambda r: f"${r['Avg_Price']:,.2f}" if r['Currency'] == 'USD' else f"{int(r['Avg_Price']):,}원", axis=1)
        df_display['현재가'] = df_port.apply(lambda r: f"${r['Current_Price']:,.2f}" if r['Currency'] == 'USD' else f"{int(r['Current_Price']):,}원", axis=1)
        
        df_display['ROI_Val'] = df_port['ROI']
        # 빨간 위삼각형, 파랑 아래삼각형 전역 통일
        df_display['수익률'] = df_port['ROI'].apply(lambda x: f"🔺 +{x:.2f}%" if x > 0 else f"🔻 {x:.2f}%" if x < 0 else f"▫️ {x:.2f}%")
        df_display['평가가치'] = df_port['Total_Value_KRW'].apply(lambda x: f"{int(x):,} 원")
        df_display['계좌'] = df_port['Account']
        
        df_display = df_display.sort_values(by='ROI_Val', ascending=False).drop(columns=['ROI_Val'])
        
        tab1, tab2, tab3 = st.tabs(["전체", "일반", "연금"])
        with tab1: st.dataframe(df_display, use_container_width=True, hide_index=True)
        with tab2: st.dataframe(df_display[df_display['계좌'] == '일반'], use_container_width=True, hide_index=True)
        with tab3: st.dataframe(df_display[df_display['계좌'] == '연금'], use_container_width=True, hide_index=True)
    else:
        st.info("조회할 장부가 비어 있습니다.")

    # --- PART 4: AI 리포트 ---
    st.markdown("---")
    st.subheader("🤖 AI 리포트 브리핑 룸")
    if latest_ai_report:
        st.caption(f"📅 리포트 공시 시점: {latest_ai_report.get('Date', 'N/A')}")
        tabs = st.tabs(["📉 퀀트", "🌍 매크로", "💎 가치투자", "🚀 텐베거"])
        sections = [("시스템 퀀트 분석", 'Quant_Opinion'), ("글로벌 매크로 환경", 'Macro_Opinion'), ("기본적 가치 분석", 'Value_Opinion'), ("텐베거 탐색", 'Ten_Bagger_Opinion')]
        
        for tab, (title, key) in zip(tabs, sections):
            with tab:
                st.markdown(f"### 📋 {title}")
                st.markdown(f"<div class='report-box'>{latest_ai_report.get(key, '내용이 없습니다.')}</div>", unsafe_allow_html=True)

except Exception as e:
    st.error(f"대시보드 구동 중 시스템 오류 발생: {e}")
