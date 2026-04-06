import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import requests
import io

# 1. 페이지 설정
st.set_page_config(page_title="US Quant Terminal v11", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #000000; }
    .main-title { color: #0f172a; font-size: 28px; font-weight: 800; text-align: center; padding: 15px; border-bottom: 2px solid #f1f5f9; }
    .sidebar-title { color: #2563eb; font-size: 17px; font-weight: 800; margin-top: 15px; }
    </style>
    """, unsafe_allow_html=True)

# 2. 공통 종목 리스트 로딩 (S&P 500 + 나스닥 100)
@st.cache_data
def get_combined_tickers():
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        sp_resp = requests.get('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies', headers=headers)
        sp500 = pd.read_html(io.StringIO(sp_resp.text))[0]['Symbol'].tolist()
        nas_resp = requests.get('https://en.wikipedia.org/wiki/Nasdaq-100', headers=headers)
        nasdaq100 = pd.read_html(io.StringIO(nas_resp.text))[4]['Ticker'].tolist()
        combined = list(set(sp500 + nasdaq100))
        return [t.replace('.', '-') for t in combined]
    except:
        return ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "BRK-B", "JPM", "V", "PG", "COST"]

# 3. 사이드바 메뉴 선택
with st.sidebar:
    st.markdown('<div class="sidebar-title">🖥️ 분석 모드 선택</div>', unsafe_allow_html=True)
    mode = st.radio("실행할 검색기를 선택하세요", ["📊 회계적 우량주 (Buffett)", "🔍 일반 우량주 검색 (v2)"])
    st.divider()

# --- 모드 1: 회계적 우량주 (Buffett v10) ---
if mode == "📊 회계적 우량주 (Buffett)":
    st.markdown('<div class="main-title">🏛️ 회계적 우량주 검색기 (Buffett v10)</div>', unsafe_allow_html=True)
    
    with st.sidebar:
        st.markdown('<div class="sidebar-title">📌 1. 공통 필터</div>', unsafe_allow_html=True)
        set_mktcap = st.number_input("최소 시가총액 ($B)", value=2.0, step=0.5, help="소형주 제외")
        
        st.markdown('<div class="sidebar-title">💰 2. 수익성 평가</div>', unsafe_allow_html=True)
        set_roe = st.slider("최소 ROE (%)", 0, 50, 10) / 100
        set_op_margin = st.slider("영업이익률 가점 (%)", 0, 30, 0, help="업종 평균 대비 초과 수익력")
        
        st.markdown('<div class="sidebar-title">⚖️ 3. 가치 평가</div>', unsafe_allow_html=True)
        set_per = st.slider("최대 PER (배)", 1.0, 150.0, 50.0)
        set_pbr = st.slider("최대 PBR (배)", 0.1, 20.0, 10.0)
        set_exp_return = st.number_input("RIM 기대수익률 (r, %)", value=5.5, step=0.1) / 100
        set_buy_margin = st.slider("매수 신호 기준 (%)", 0, 50, 0)
        
        st.markdown('<div class="sidebar-title">🛡️ 4. 재무 건전성</div>', unsafe_allow_html=True)
        set_debt = st.slider("최대 부채비율 (%)", 0, 300, 150)
        set_ocf_ni = st.checkbox("OCF > NI 검증", value=False)
        set_fcf = st.checkbox("FCF 발생 필수", value=False)
        
        start_scan = st.button("📊 버핏 모드 검색 시작", type="primary", use_container_width=True)

    if start_scan:
        all_tickers = get_combined_tickers()
        results = []
        progress = st.progress(0)
        for i, t in enumerate(all_tickers):
            progress.progress((i + 1) / len(all_tickers))
            try:
                s = yf.Ticker(t); inf = s.info
                equity = inf.get('totalStockholderEquity'); shares = inf.get('sharesOutstanding')
                roe = inf.get('returnOnEquity'); price = inf.get('currentPrice')
                if not all([equity, shares, roe, price]): continue
                
                total_debt = inf.get('totalDebt') or 0
                debt_ratio = (total_debt / equity) * 100 if equity > 0 else 0
                if debt_ratio > set_debt or roe < set_roe: continue
                
                # RIM 계산
                ent_val = equity + (equity * (roe - set_exp_return) / set_exp_return)
                fair_p = ent_val / shares
                margin = ((fair_p / price) - 1) * 100
                if margin < set_buy_margin: continue

                results.append({
                    "신호": "🟢 매수" if margin >= 10 else "🟡 보유", "티커": t, "기업명": inf.get('shortName'),
                    "안전마진": f"{margin:.1f}%", "현재가": f"${price:.2f}", "ROE": f"{roe:.1%}", "raw_margin": margin
                })
            except: continue
        st.session_state['buffett_data'] = pd.DataFrame(results)

    if 'buffett_data' in st.session_state:
        df = st.session_state['buffett_data']
        st.dataframe(df.sort_values('raw_margin', ascending=False).drop('raw_margin', axis=1), use_container_width=True)

# --- 모드 2: 일반 우량주 검색 (v2) ---
elif mode == "🔍 일반 우량주 검색 (v2)":
    st.markdown('<div class="main-title">🔍 일반 우량주 검색기 (v2)</div>', unsafe_allow_html=True)
    
    with st.sidebar:
        st.markdown('<div class="sidebar-title">⚙️ 투자 필터 설정</div>', unsafe_allow_html=True)
        max_per = st.slider("최대 PER", 1, 50, 28)
        min_roe = st.slider("최소 ROE (%)", 0, 50, 12) / 100
        max_pbr = st.slider("최대 PBR", 0.1, 5.0, 1.5)
        filter_ebitda = st.checkbox("EBITDA 3년 연속 상승 필수", value=False)
        start_scan_v2 = st.button("📊 일반 검색 시작", type="primary", use_container_width=True)

    if start_scan_v2:
        all_tickers = get_combined_tickers()
        results_v2 = []
        progress_v2 = st.progress(0)
        for i, t in enumerate(all_tickers):
            progress_v2.progress((i + 1) / len(all_tickers))
            try:
                s = yf.Ticker(t); inf = s.info
                pe = inf.get('trailingPE', 0); pbr = inf.get('priceToBook', 0); roe = inf.get('returnOnEquity', 0)
                if 0 < pe <= max_per and roe >= min_roe and 0 < pbr <= max_pbr:
                    if filter_ebitda:
                        ebs = s.income_stmt.loc['EBITDA']
                        if not (ebs.iloc[0] > ebs.iloc[1] > ebs.iloc[2]): continue
                    results_v2.append({"티커": t, "기업명": inf.get('shortName'), "PER": round(pe, 1), "ROE": f"{roe:.1%}", "PBR": round(pbr, 2)})
            except: continue
        st.session_state['v2_data'] = pd.DataFrame(results_v2)

    if 'v2_data' in st.session_state:
        st.dataframe(st.session_state['v2_data'], use_container_width=True)
