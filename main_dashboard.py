import streamlit as st
import pandas as pd
import os
import json
import requests
import plotly.express as px
from datetime import datetime
from dotenv import load_dotenv
from src.sheets_client import get_sheet_client

# --- 페이지 기본 설정 ---
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
        st.error(f"인증서 동기화 중 오류 발생: {e}")

load_dotenv()
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID") or st.secrets.get("SPREADSHEET_ID")

def get_usd_krw_rate():
    try:
        res = requests.get("https://open.er-api.com/v6/latest/USD", timeout=3)
        if res.status_code == 200:
            return float(res.json()["rates"]["KRW"])
    except Exception:
        pass
    return 1350.0

# 💡 [핵심 교정] 어떤 구글 시트 오류에도 무너지지 않는 무적 파싱 엔진
@st.cache_data(ttl=30)
def load_all_dashboard_data():
    client = get_sheet_client()
    doc = client.open_by_key(SPREADSHEET_ID)
    
    def safe_get_df(sheet_name):
        try:
            sheet = doc.worksheet(sheet_name)
            vals = sheet.get_all_values()
            if not vals:
                return pd.DataFrame()
                
            # 1단계: 시트를 뒤져서 'Date', 'Ticker', '종목' 등의 키워드가 있는 진짜 머리글 위치를 찾음
            header_idx = 0
            for i, row in enumerate(vals):
                row_str = "".join([str(x).lower() for x in row])
                if 'ticker' in row_str or '종목' in row_str or 'date' in row_str or '날짜' in row_str:
                    header_idx = i
                    break
                    
            headers = vals[header_idx]
            clean_headers = [str(h).strip() if str(h).strip() else f"Unnamed_{j}" for j, h in enumerate(headers)]
            
            # 2단계: 머리글 밑의 데이터를 추출하고, 빈칸을 패딩하여 완벽한 표(DataFrame)로 강제 조립
            if len(vals) > header_idx + 1:
                data = vals[header_idx+1:]
                data = [row + [''] * (len(clean_headers) - len(row)) for row in data]
                data = [row[:len(clean_headers)] for row in data]
                df = pd.DataFrame(data, columns=clean_headers)
                
                # 완전히 텅 빈 깡통 행(찌꺼기) 제거
                df = df[df.apply(lambda r: "".join(r.astype(str)).strip() != "", axis=1)]
                return df
            return pd.DataFrame(columns=clean_headers)
        except Exception as e:
            st.error(f"[{sheet_name}] 데이터 로딩 중 예외 발생: {e}")
            return pd.DataFrame()

    df_portfolio = safe_get_df("Portfolio")
    df_history = safe_get_df("History")
    
    try:
        ai_records = doc.worksheet("AI_Reports").get_all_records()
        df_ai = pd.DataFrame(ai_records)
        latest_ai_report = df_ai.iloc[-1] if not df_ai.empty else None
    except Exception:
        latest_ai_report = None
        
    return df_portfolio, df_history, latest_ai_report

def find_column(df, possible_names):
    if df is None or df.empty:
        return None
    for name in possible_names:
        for col in df.columns:
            if str(col).strip().lower() == name.lower():
                return col
    return None

# --- 대시보드 렌더링 ---
st.title("🏦 포트폴리오 자산 운용 콕핏")

try:
    usd_krw = get_usd_krw_rate()
    st.caption(f"📡 실시간 고시 환율 기준: 1 USD = {usd_krw:,.2f} KRW")

    with st.spinner("인프라 데이터 동기화 중..."):
        df_portfolio, df_history, latest_ai_report = load_all_dashboard_data()

    # --- 전일 대비 증감 연산 로직 ---
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
            df_h_clean['parsed_date'] = pd.to_datetime(df_h_clean[date_col], errors='coerce').dt.date
            df_h_clean = df_h_clean.dropna(subset=['parsed_date'])
            unique_dates = sorted(df_h_clean['parsed_date'].unique())
            
            if len(unique_dates) < 2: 
                return 0, 0
                
            latest_date = unique_dates[-1]
            prev_date = unique_dates[-2]
            
            df_h_clean[val_col] = pd.to_numeric(df_h_clean[val_col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            
            def sum_val_for_date(target_date):
                target_df = df_h_clean[df_h_clean['parsed_date'] == target_date]
                if account_filter:
                    target_df = target_df[target_df[acc_col_h].astype(str).str.strip() == account_filter]
                return target_df[val_col].sum()
                
            curr_sum = sum_val_for_date(latest_date)
            prev_sum = sum_val_for_date(prev_date)
            
            diff = curr_sum - prev_sum
            pct = (diff / prev_sum * 100) if prev_sum != 0 else 0
            return diff, pct
        except Exception:
            return 0, 0

    ticker_col = find_column(df_portfolio, ['ticker', '종목', '종목코드'])
    shares_col = find_column(df_portfolio, ['shares', '수량', '보유수량'])
    price_col = find_column(df_portfolio, ['current_price', '현재가', '가격'])
    avg_col = find_column(df_portfolio, ['avg_price', '평단가', '매입단가'])
    curr_col = find_column(df_portfolio, ['currency', '통화'])
    acc_col = find_column(df_portfolio, ['account', '계좌', '계좌구분'])
    name_col = find_column(df_portfolio, ['stock_name', '종목명', '회사명'])

    total_asset, normal_asset, pension_asset = 0, 0, 0
    total_diff, total_pct = get_delta_fixed(df_history)
    normal_diff, normal_pct = get_delta_fixed(df_history, "일반")
    pension_diff, pension_pct = get_delta_fixed(df_history, "연금")

    if not df_portfolio.empty and ticker_col and shares_col and price_col and avg_col:
        df_portfolio[shares_col] = pd.to_numeric(df_portfolio[shares_col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
        df_portfolio[price_col] = pd.to_numeric(df_portfolio[price_col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
        df_portfolio[avg_col] = pd.to_numeric(df_portfolio[avg_col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
        
        if not curr_col: df_portfolio['Currency'] = df_portfolio[ticker_col].apply(lambda x: 'USD' if str(x).isalpha() else 'KRW')
        if not acc_col: df_portfolio['Account'] = '일반'

        df_portfolio['Total_Value_KRW'] = df_portfolio.apply(
            lambda r: r[shares_col] * r[price_col] * usd_krw if str(r[find_column(df_portfolio, ['currency', 'Currency'])]).upper() == 'USD' else r[shares_col] * r[price_col],
            axis=1
        )
        
        df_portfolio['Total_Cost_KRW'] = df_portfolio.apply(
            lambda r: r[shares_col] * r[avg_col] * usd_krw if str(r[find_column(df_portfolio, ['currency', 'Currency'])]).upper() == 'USD' else r[shares_col] * r[avg_col],
            axis=1
        )
        df_portfolio['수익률_수치'] = df_portfolio.apply(
            lambda r: ((r['Total_Value_KRW'] - r['Total_Cost_KRW']) / r['Total_Cost_KRW'] * 100) if r['Total_Cost_KRW'] != 0 else 0.0,
            axis=1
        )
        
        total_asset = df_portfolio['Total_Value_KRW'].sum()
        normal_asset = df_portfolio[df_portfolio[find_column(df_portfolio, ['account', 'Account'])] == '일반']['Total_Value_KRW'].sum()
        pension_asset = df_portfolio[df_portfolio[find_column(df_portfolio, ['account', 'Account'])] == '연금']['Total_Value_KRW'].sum()

    # ==========================================
    # 💰 PART 1: 커스텀 HTML KPI 전광판
    # ==========================================
    def render_metric_card(title, value, diff, pct):
        if diff > 0:
            color, arrow, sign = "#FF4B4B", "🔺", "+"
        elif diff < 0:
            color, arrow, sign = "#1C83E1", "🔻", ""
        else:
            color, arrow, sign = "#888888", "▫️", "+"
            
        html = f"""
        <div style="background-color: #1e222b; padding: 20px; border-radius: 8px; border: 1px solid #2e3440; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">
            <p style="color: #b0b5c0; font-size: 15px; margin-bottom: 5px; font-weight: 600;">{title}</p>
            <h2 style="color: white; margin: 0; font-size: 32px; letter-spacing: -0.5px;">{value:,.0f} <span style="font-size:16px; font-weight:normal; color:#888;">원</span></h2>
            <p style="color: {color}; margin-top: 8px; font-size: 15px; margin-bottom: 0; font-weight: 500;">{arrow} {sign}{diff:,.0f} 원 ({sign}{pct:.2f}%)</p>
        </div>
        """
        return html

    m1, m2, m3 = st.columns(3)
    with m1: st.markdown(render_metric_card("💰 총 자산 합계", total_asset, total_diff, total_pct), unsafe_allow_html=True)
    with m2: st.markdown(render_metric_card("💵 일반 주식계좌 자산", normal_asset, normal_diff, normal_pct), unsafe_allow_html=True)
    with m3: st.markdown(render_metric_card("🛡️ 연금저축/IRP 자산", pension_asset, pension_diff, pension_pct), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ==========================================
    # 📈 PART 2: 자산 시계열 및 비중 차트
    # ==========================================
    g1, g2 = st.columns([6, 4])
    
    with g1:
        st.subheader("📈 자산 성장 타임라인")
        val_col_hist = find_column(df_history, ['total_value_krw', 'value', '평가가치'])
        date_col_hist = find_column(df_history, ['date', '날짜', '일자'])
        acc_col_hist = find_column(df_history, ['account', '계좌', '계좌구분'])
        
        if not df_history.empty and val_col_hist and date_col_hist and acc_col_hist:
            try:
                df_h_chart = df_history.copy()
                df_h_chart[date_col_hist] = pd.to_datetime(df_h_chart[date_col_hist], errors='coerce').dt.date
                df_h_chart = df_h_chart.dropna(subset=[date_col_hist])
                df_h_chart[val_col_hist] = pd.to_numeric(df_h_chart[val_col_hist].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
                
                df_timeline = df_h_chart.groupby([date_col_hist, acc_col_hist])[val_col_hist].sum().unstack(fill_value=0)
                df_timeline['총자산'] = df_timeline.sum(axis=1)
                st.line_chart(df_timeline)
            except Exception as e:
                st.error(f"차트 렌더링 중 오류: {e}")
        else:
            st.info("📅 아직 데이터 축적량이 부족합니다. 역사 데이터 곡선이 곧 형성됩니다.")

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
            fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), showlegend=True, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # ==========================================
    # 📊 PART 3: 자산 세부 보유 현황
    # ==========================================
    st.subheader("📊 핵심 포트폴리오 스냅샷 (수익률 순 정렬)")
    if not df_portfolio.empty:
        df_display = pd.DataFrame()
        df_display['종목명'] = df_portfolio[name_col].fillna(df_portfolio[ticker_col])
        df_display['보유주식수'] = df_portfolio[shares_col].apply(lambda x: f"{int(x):,}" if float(x).is_integer() else f"{x:,.2f}")
        
        df_display['매수가'] = df_portfolio.apply(lambda r: f"${r[avg_col]:,.2f}" if str(r[find_column(df_portfolio, ['currency', 'Currency'])]).upper() == 'USD' else f"{int(r[avg_col]):,}원", axis=1)
        df_display['현재가'] = df_portfolio.apply(lambda r: f"${r[price_col]:,.2f}" if str(r[find_column(df_portfolio, ['currency', 'Currency'])]).upper() == 'USD' else f"{int(r[price_col]):,}원", axis=1)
        
        df_display['_raw_roi'] = df_portfolio['수익률_수치']
        df_display['수익률'] = df_portfolio['수익률_수치'].apply(lambda x: f"🔺 {x:+.2f}%" if x > 0 else f"🔻 {x:+.2f}%" if x < 0 else f"▫️ {x:.2f}%")
        df_display['평가가치'] = df_portfolio['Total_Value_KRW'].apply(lambda x: f"{int(x):,} 원")
        df_display['계좌구분'] = df_portfolio[find_column(df_portfolio, ['account', 'Account'])]
        
        df_display = df_display.sort_values(by='_raw_roi', ascending=False).drop(columns=['_raw_roi'])
        
        account_tab1, account_tab2, account_tab3 = st.tabs(["전체 자산 스냅샷", "일반 주식 자산", "연금저축/IRP 자산"])
        with account_tab1:
            st.dataframe(df_display, use_container_width=True, hide_index=True)
        with account_tab2:
            st.dataframe(df_display[df_display['계좌구분'] == '일반'], use_container_width=True, hide_index=True)
        with account_tab3:
            st.dataframe(df_display[df_display['계좌구분'] == '연금'], use_container_width=True, hide_index=True)
    else:
        st.info("조회할 세부 장부가 비어 있습니다.")

    st.markdown("---")
    st.subheader("🤖 AI 리포트 브리핑 룸")
    if latest_ai_report is not None:
        st.caption(f"📅 리포트 공시 시점: {latest_ai_report.get('Date', 'N/A')}")
        tab1, tab2, tab3, tab4 = st.tabs(["📉 퀀트", "🌍 매크로", "💎 가치투자", "🚀 텐베거"])
        def render_structured_report(title, raw_content):
            st.markdown(f"### 📋 {title}")
            st.markdown(f"<div class='report-box'>{raw_content}</div>", unsafe_allow_html=True)
        with tab1: render_structured_report("퀀트 포지셔닝", latest_ai_report.get('Quant_Opinion', '데이터 없음'))
        with tab2: render_structured_report("매크로 포지셔닝", latest_ai_report.get('Macro_Opinion', '데이터 없음'))
        with tab3: render_structured_report("밸류에이션 점검", latest_ai_report.get('Value_Opinion', '데이터 없음'))
        with tab4: render_structured_report("텐베거 탐색", latest_ai_report.get('Ten_Bagger_Opinion', '데이터 없음'))

    # ==========================================
    # 🛠️ 엔지니어 전용 시스템 디버거 (최하단 은닉)
    # ==========================================
    with st.expander("🛠️ 시스템 디버깅 콘솔 (데이터 스캐닝 결과 확인)"):
        st.write("✅ **Portfolio 시트 인식 상태:**", f"{len(df_portfolio)}행 로드됨")
        st.write("✅ **History 시트 인식 상태:**", f"{len(df_history)}행 로드됨")
        if not df_history.empty:
            st.write("➡️ **History 컬럼 구조:**", df_history.columns.tolist())
            st.dataframe(df_history.tail(3))
        else:
            st.error("❌ History 데이터를 파이썬이 전혀 읽지 못하고 있습니다.")

except Exception as e:
    st.error("대시보드 엔진 구동 중 예외가 발생했습니다.")
    st.exception(e)
