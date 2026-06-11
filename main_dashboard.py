import streamlit as st
import pandas as pd
import os
import json
import requests
import datetime
import plotly.express as px
import yfinance as yf
import FinanceDataReader as fdr
from google import genai
from google.genai import types
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
    .report-box { background-color: #1a1c23; padding: 25px; border-radius: 10px; border-left: 5px solid #FF4B4B; margin-bottom: 20px; line-height: 1.6; }
    </style>
""", unsafe_allow_html=True)

if "google_credentials" in st.secrets:
    try:
        with open("credentials.json", "w", encoding="utf-8") as f:
            json.dump(dict(st.secrets["google_credentials"]), f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"인증서 설정 오류: {e}")

load_dotenv()
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID") or st.secrets.get("SPREADSHEET_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY")

ai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

def get_usd_krw_rate():
    try:
        res = requests.get("https://open.er-api.com/v6/latest/USD", timeout=3)
        if res.status_code == 200: return float(res.json()["rates"]["KRW"])
    except: pass
    return 1350.0

@st.cache_data(ttl=30)
def load_data():
    client = get_sheet_client()
    doc = client.open_by_key(SPREADSHEET_ID)
    def fetch_sheet(name):
        try:
            worksheet = doc.worksheet(name)
            vals = worksheet.get_all_values()
            if not vals: return pd.DataFrame()
            df = pd.DataFrame(vals[1:], columns=vals[0])
            df.columns = df.columns.astype(str).str.strip()
            return df
        except: return pd.DataFrame()

    return fetch_sheet("Portfolio"), fetch_sheet("History"), (doc.worksheet("AI_Reports").get_all_records()[-1] if doc.worksheet("AI_Reports").get_all_records() else None)

def clean_numeric(series):
    cleaned = series.astype(str).str.replace(r'[^\d\.-]', '', regex=True)
    return pd.to_numeric(cleaned, errors='coerce').fillna(0)

def calc_delta(df_hist, account_type=None):
    if df_hist.empty or 'Date' not in df_hist.columns or 'Total_Value_KRW' not in df_hist.columns: return 0, 0
    df = df_hist.copy()
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.normalize()
    df['Total_Value_KRW'] = clean_numeric(df['Total_Value_KRW'])
    df = df.dropna(subset=['Date'])
    if account_type and 'Account' in df.columns: df = df[df['Account'].str.strip() == account_type]
    daily_sum = df.groupby('Date')['Total_Value_KRW'].sum().sort_index()
    if len(daily_sum) < 2: return 0, 0
    diff = daily_sum.iloc[-1] - daily_sum.iloc[-2]
    pct = (diff / daily_sum.iloc[-2] * 100) if daily_sum.iloc[-2] != 0 else 0
    return diff, pct

# ==========================================
# 4. 하이브리드 섹터 분류 (API + ML Model)
# ==========================================
@st.cache_data(ttl=604800) # 한 번 분류한 데이터는 1주일(604800초)간 캐싱하여 속도 극대화
def get_smart_sectors(portfolio_dicts):
    sector_map = {}
    unclassified = []
    
    # 1. 미국 주식 대상 yfinance GICS API 직접 추출
    for row in portfolio_dicts:
        t = row['Ticker']
        n = row['Stock_Name']
        c = row['Currency']
        
        if c == 'USD' and str(t).isalpha():
            try:
                info = yf.Ticker(t).info
                sec = info.get('sector', '')
                ind = info.get('industry', '')
                
                # 반도체와 바이오는 하위 산업군(industry)까지 검사하여 명확히 분리
                if 'Semiconductor' in ind:
                    sector_map[t] = '반도체 (Semiconductors)'
                elif 'Biotech' in ind or 'Health' in sec:
                    sector_map[t] = '바이오/헬스케어 (Healthcare)'
                elif sec:
                    sector_map[t] = sec
                    continue
            except:
                pass
        
        # API 조회가 안되는 ETF나 한국 주식은 미분류로 적재
        if t not in sector_map:
            unclassified.append({"ticker": t, "name": n, "currency": c})
            
    # 2. 미분류 종목 대상 Gemini Zero-shot 머신러닝 분류
    if unclassified and ai_client:
        prompt = """
        다음의 주식/ETF 종목 리스트를 분석하여, 각 종목을 아래 카테고리 중 가장 적합한 하나로만 맵핑해줘.
        [반도체, 바이오/헬스케어, 빅테크/IT, 배당/인컴, 시장지수, 금융, 소비재, 자동차/모빌리티, 안전자산, 채권, 산업재, 기타]
        
        오직 아래의 JSON 형식으로만 반환할 것. 다른 설명은 절대 추가하지 마.
        {"AAPL": "빅테크/IT", "005930": "반도체", "TIGER 200": "시장지수"}
        
        종목 리스트:
        """ + str(unclassified)
        
        try:
            res = ai_client.models.generate_content(
                model='gemini-3.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            ml_result = json.loads(res.text)
            sector_map.update(ml_result)
        except Exception as e:
            print("ML Classification Error:", e)
            
    return sector_map

st.title("🏦 포트폴리오 자산 운용 콕핏")

try:
    usd_krw = get_usd_krw_rate()
    st.caption(f"📡 실시간 고시 환율 기준: 1 USD = {usd_krw:,.2f} KRW")

    with st.spinner("데이터 동기화 및 ML 섹터 분류 중..."):
        df_port_raw, df_hist_raw, latest_ai_report = load_data()

    total_diff, total_pct = calc_delta(df_hist_raw)
    normal_diff, normal_pct = calc_delta(df_hist_raw, "일반")
    pension_diff, pension_pct = calc_delta(df_hist_raw, "연금")
    total_asset, normal_asset, pension_asset = 0, 0, 0

    df_port = df_port_raw.copy()
    if not df_port.empty:
        df_port['Shares'] = clean_numeric(df_port.get('Shares', pd.Series([0]*len(df_port))))
        df_port['Current_Price'] = clean_numeric(df_port.get('Current_Price', pd.Series([0]*len(df_port))))
        df_port['Avg_Price'] = clean_numeric(df_port.get('Avg_Price', pd.Series([0]*len(df_port))))
        df_port['Currency'] = df_port.get('Currency', pd.Series(['KRW']*len(df_port))).astype(str).str.strip().str.upper()
        df_port['Account'] = df_port.get('Account', pd.Series(['일반']*len(df_port))).astype(str).str.strip()

        def get_krw_val(row, price_col):
            return row[price_col] * row['Shares'] * usd_krw if row['Currency'] == 'USD' else row[price_col] * row['Shares']

        df_port['Total_Value_KRW'] = df_port.apply(lambda r: get_krw_val(r, 'Current_Price'), axis=1)
        df_port['Total_Cost_KRW'] = df_port.apply(lambda r: get_krw_val(r, 'Avg_Price'), axis=1)
        df_port['ROI'] = df_port.apply(lambda r: ((r['Total_Value_KRW'] - r['Total_Cost_KRW']) / r['Total_Cost_KRW'] * 100) if r['Total_Cost_KRW'] > 0 else 0, axis=1)
        
        # 하이브리드 섹터 매핑 적용
        minimal_data = df_port[['Ticker', 'Stock_Name', 'Currency']].to_dict('records')
        sector_mapping = get_smart_sectors(minimal_data)
        df_port['Sector'] = df_port['Ticker'].apply(lambda x: sector_mapping.get(str(x), '기타 산업군'))

        total_asset = df_port['Total_Value_KRW'].sum()
        normal_asset = df_port[df_port['Account'] == '일반']['Total_Value_KRW'].sum()
        pension_asset = df_port[df_port['Account'] == '연금']['Total_Value_KRW'].sum()

    def render_card(title, value, diff, pct=None, unit="원"):
        color, arrow, sign = ("#FF4B4B", "▲", "+") if diff > 0 else ("#1C83E1", "▼", "") if diff < 0 else ("#888888", "-", "")
        value_fmt = f"{value:,.0f}" if unit == "원" else f"{value:.2f}"
        diff_fmt = f"{diff:,.0f} {unit}" if unit == "원" else f"{diff:.2f}%p"
        pct_str = f" ({sign}{pct:.2f}%)" if pct is not None else ""
        return f"""<div class="metric-card"><p class="metric-title">{title}</p><h2 class="metric-value">{value_fmt} <span class="metric-unit">{unit}</span></h2><p style="color: {color}; margin-top: 8px; font-size: 15px; margin-bottom: 0; font-weight: 500;">{arrow} {sign}{diff_fmt}{pct_str}</p></div>"""

    # --- 매크로 지표 패널 ---
    st.markdown("### 🌍 글로벌 매크로 지표 (실시간)")
    macro_cols = st.columns(4)
    @st.cache_data(ttl=3600)
    def fetch_macro_indicators():
        try:
            tickers = {"5Y": "^FVX", "10Y": "^TNX", "30Y": "^TYX", "VIX": "^VIX"}
            res = {}
            for name, t in tickers.items():
                df = yf.Ticker(t).history(period="2d")
                val = df['Close'].iloc[-1] if len(df) >= 1 else 0
                diff = val - df['Close'].iloc[-2] if len(df) >= 2 else 0
                res[name] = (val, diff)
            return res
        except: return {"5Y":(0,0), "10Y":(0,0), "30Y":(0,0), "VIX":(0,0)}

    macro_data = fetch_macro_indicators()
    with macro_cols[0]: st.markdown(render_card("🇺🇸 미 5년물 국채", macro_data["5Y"][0], macro_data["5Y"][1], unit="%"), unsafe_allow_html=True)
    with macro_cols[1]: st.markdown(render_card("🇺🇸 미 10년물 국채", macro_data["10Y"][0], macro_data["10Y"][1], unit="%"), unsafe_allow_html=True)
    with macro_cols[2]: st.markdown(render_card("🇺🇸 미 30년물 국채", macro_data["30Y"][0], macro_data["30Y"][1], unit="%"), unsafe_allow_html=True)
    with macro_cols[3]: st.markdown(render_card("📉 VIX (공포지수)", macro_data["VIX"][0], macro_data["VIX"][1], unit="pt"), unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # --- 자산 전광판 ---
    col1, col2, col3 = st.columns(3)
    with col1: st.markdown(render_card("💰 총 자산 합계", total_asset, total_diff, total_pct, "원"), unsafe_allow_html=True)
    with col2: st.markdown(render_card("💵 일반 주식계좌 자산", normal_asset, normal_diff, normal_pct, "원"), unsafe_allow_html=True)
    with col3: st.markdown(render_card("🛡️ 연금저축/IRP 자산", pension_asset, pension_diff, pension_pct, "원"), unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # --- 시계열 & 섹터 트리맵 ---
    g1, g2 = st.columns([5, 5])
    with g1:
        st.subheader("📈 자산 성장 타임라인")
        if not df_hist_raw.empty and 'Date' in df_hist_raw.columns:
            df_chart = df_hist_raw.copy()
            df_chart['Date'] = pd.to_datetime(df_chart['Date'], errors='coerce').dt.normalize()
            df_chart['Total_Value_KRW'] = clean_numeric(df_chart['Total_Value_KRW'])
            df_chart['Account'] = df_chart.get('Account', '일반').astype(str).str.strip()
            df_chart = df_chart.dropna(subset=['Date'])
            if not df_chart.empty:
                df_timeline = df_chart.groupby(['Date', 'Account'])['Total_Value_KRW'].sum().unstack(fill_value=0)
                df_timeline['총 자산'] = df_timeline.sum(axis=1)
                st.line_chart(df_timeline)
            else: st.info("차트를 그릴 수 있는 유효한 날짜 데이터가 없습니다.")
        else: st.info("📅 아직 데이터 축적량이 부족합니다.")

    with g2:
        st.subheader("🍕 ML 기반 섹터별 심층 비중 (Treemap)")
        if not df_port.empty:
            # 수익률(ROI) 기준 컬러 매핑 (파랑=하락, 빨강=상승)
            fig = px.treemap(
                df_port, 
                path=[px.Constant("전체 포트폴리오"), 'Sector', 'Stock_Name'], 
                values='Total_Value_KRW',
                color='ROI',
                color_continuous_scale=['#1C83E1', '#2e3440', '#FF4B4B'],
                color_continuous_midpoint=0
            )
            fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # --- 벤치마크 & 리스크 모니터링 ---
    st.subheader("🛡️ 리스크 관리 & 벤치마크 (1Y)")
    st.caption("내 포트폴리오의 과거 데이터가 30일 이상 축적되면 포트폴리오 자체의 MDD와 Beta 연산도 이곳에 활성화됩니다.")
    
    @st.cache_data(ttl=3600)
    def fetch_benchmarks():
        try:
            end = datetime.datetime.now()
            start = end - datetime.timedelta(days=365)
            # S&P 500
            df_spy = yf.download('^GSPC', start=start, end=end, progress=False)
            spy_close = df_spy['Close'] if isinstance(df_spy.columns, pd.Index) else df_spy.iloc[:, 0]
            
            # KOSPI
            df_kospi = fdr.DataReader('KS11', start, end)
            kospi_close = df_kospi['Close']
            
            def get_risk_metrics(series):
                if series.empty: return 0, 0, 0
                ret = (series.iloc[-1] / series.iloc[0] - 1) * 100
                roll_max = series.cummax()
                drawdown = (series / roll_max - 1) * 100
                return ret, drawdown.min(), drawdown.iloc[-1]
                
            spy_ret, spy_mdd, spy_cdd = get_risk_metrics(spy_close)
            kospi_ret, kospi_mdd, kospi_cdd = get_risk_metrics(kospi_close)
            return spy_ret, spy_mdd, spy_cdd, kospi_ret, kospi_mdd, kospi_cdd
        except: return 0,0,0, 0,0,0

    sr, sm, sc, kr, km, kc = fetch_benchmarks()
    bm_cols = st.columns(2)
    with bm_cols[0]:
        st.markdown(f"""
        <div class="metric-card" style="border-left: 5px solid #FBC02D;">
            <p class="metric-title">🇺🇸 S&P 500 (1년 지표)</p>
            <p>누적 수익률: <b style="color: {'#FF4B4B' if sr>0 else '#1C83E1'};">{'+' if sr>0 else ''}{sr:.2f}%</b></p>
            <p>최대 낙폭 (MDD): <b style="color: #1C83E1;">{sm:.2f}%</b></p>
            <p>현재 고점 대비: <b>{sc:.2f}%</b></p>
        </div>
        """, unsafe_allow_html=True)
    with bm_cols[1]:
        st.markdown(f"""
        <div class="metric-card" style="border-left: 5px solid #1C83E1;">
            <p class="metric-title">🇰🇷 KOSPI (1년 지표)</p>
            <p>누적 수익률: <b style="color: {'#FF4B4B' if kr>0 else '#1C83E1'};">{'+' if kr>0 else ''}{kr:.2f}%</b></p>
            <p>최대 낙폭 (MDD): <b style="color: #1C83E1;">{km:.2f}%</b></p>
            <p>현재 고점 대비: <b>{kc:.2f}%</b></p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # --- 핵심 포트폴리오 스냅샷 (UI 극대화) ---
    st.subheader("📊 핵심 포트폴리오 스냅샷")
    if not df_port.empty:
        df_display = pd.DataFrame()
        df_display['섹터(ML)'] = df_port['Sector']
        df_display['종목명'] = df_port['Stock_Name']
        df_display['보유수량'] = df_port['Shares'].apply(lambda x: f"{int(x):,}" if float(x).is_integer() else f"{x:,.2f}")
        df_display['매수가'] = df_port.apply(lambda r: f"${r['Avg_Price']:,.2f}" if r['Currency'] == 'USD' else f"{int(r['Avg_Price']):,}원", axis=1)
        df_display['현재가'] = df_port.apply(lambda r: f"${r['Current_Price']:,.2f}" if r['Currency'] == 'USD' else f"{int(r['Current_Price']):,}원", axis=1)
        
        df_display['ROI_raw'] = df_port['ROI']
        df_display['계좌'] = df_port['Account']
        
        df_display = df_display.sort_values(by='ROI_raw', ascending=False)
        df_display['수익률'] = df_display['ROI_raw'].apply(lambda x: f"▲ +{x:.2f}%" if x > 0 else f"▼ {x:.2f}%" if x < 0 else f"- {x:.2f}%")
        
        display_columns = ['섹터(ML)', '종목명', '보유수량', '매수가', '현재가', '수익률']
        
        def style_roi_table(val):
            if '▲' in str(val): return 'color: #FF4B4B; font-weight: bold; background-color: rgba(255, 75, 75, 0.1);'
            elif '▼' in str(val): return 'color: #1C83E1; font-weight: bold; background-color: rgba(28, 131, 225, 0.1);'
            return 'color: #888888;'
            
        tab1, tab2, tab3 = st.tabs(["전체", "일반", "연금"])
        with tab1: st.dataframe(df_display[display_columns].style.map(style_roi_table, subset=['수익률']), use_container_width=True, hide_index=True)
        with tab2: st.dataframe(df_display[df_display['계좌'] == '일반'][display_columns].style.map(style_roi_table, subset=['수익률']), use_container_width=True, hide_index=True)
        with tab3: st.dataframe(df_display[df_display['계좌'] == '연금'][display_columns].style.map(style_roi_table, subset=['수익률']), use_container_width=True, hide_index=True)
    else:
        st.info("조회할 장부가 비어 있습니다.")

    st.markdown("---")

    # --- AI 리포트 ---
    st.subheader("🤖 AI 리포트 브리핑 룸")
    if latest_ai_report:
        st.caption(f"📅 리포트 공시 시점: {latest_ai_report.get('Date', 'N/A')}")
        tabs = st.tabs(["📉 퀀트", "🌍 매크로", "💎 가치투자", "🚀 텐베거"])
        sections = [("시스템 퀀트 분석", 'Quant_Opinion'), ("글로벌 매크로 환경", 'Macro_Opinion'), ("기본적 가치 분석", 'Value_Opinion'), ("텐베거 탐색", 'Ten_Bagger_Opinion')]
        
        for tab, (title, key) in zip(tabs, sections):
            with tab:
                st.markdown(f"<div class='report-box'>{latest_ai_report.get(key, '내용이 없습니다.')}</div>", unsafe_allow_html=True)

except Exception as e:
    st.error(f"대시보드 구동 중 시스템 오류 발생: {e}")
