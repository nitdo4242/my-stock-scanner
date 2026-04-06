import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import requests
import io

# 1. 페이지 설정
st.set_page_config(page_title="US Quant Terminal v9", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #000000; }
    .main-title { color: #0f172a; font-size: 28px; font-weight: 800; text-align: center; padding: 15px; border-bottom: 2px solid #f1f5f9; }
    .sidebar-title { color: #1e293b; font-size: 17px; font-weight: 800; margin-top: 15px; color: #2563eb; }
    </style>
    """, unsafe_allow_html=True)

st.markdown('<div class="main-title">🏛️ 우량주 검색기</div>', unsafe_allow_html=True)

# 2. 종목 리스트 로딩 (S&P 500 + 나스닥 100)
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

# 3. 사이드바: 카테고리별 필터 (부채비율 하한선 10% 반영)
with st.sidebar:
    if st.button("🔄 모든 설정 초기화", use_container_width=True):
        st.session_state.clear()
        st.rerun()
    
    st.divider()

    # --- 1. 공통 필터 ---
    st.markdown('<div class="sidebar-title">📌 1. 공통 필터</div>', unsafe_allow_html=True)
    set_mktcap = st.number_input("최소 시가총액 ($B)", value=2.0, step=0.5, help="소형주 제외 및 유동성 확보")

    # --- 2. 수익성 평가 ---
    st.markdown('<div class="sidebar-title">💰 2. 수익성 평가</div>', unsafe_allow_html=True)
    set_roe = st.slider("최소 ROE (%)", 0, 50, 15, help="자본 효율성 측정") / 100
    set_op_margin = st.slider("영업이익률 가점 (%)", 0, 30, 5, help="업종 평균 대비 초과 수익력")

    # --- 3. 가치 평가 ---
    st.markdown('<div class="sidebar-title">⚖️ 3. 가치 평가</div>', unsafe_allow_html=True)
    set_per = st.slider("최대 PER (배)", 1.0, 100.0, 40.0, help="이익 대비 주가 수준")
    set_pbr = st.slider("최대 PBR (배)", 0.1, 15.0, 8.0, help="자산 대비 주가 수준")
    set_exp_return = st.number_input("RIM 기대수익률 (r, %)", value=6.0, step=0.1, help="요구수익률") / 100
    # [사용자 요청] 매수 신호 기준 하한선 10%
    set_buy_margin = st.slider("매수 신호 기준 (%)", 10, 50, 10, help="최소 10% 이상의 안전 마진 필수")

    # --- 4. 재무 건전성 ---
    st.markdown('<div class="sidebar-title">🛡️ 4. 재무 건전성</div>', unsafe_allow_html=True)
    # [사용자 요청] 부채비율 하한선 10% 적용
    set_debt = st.slider("최대 부채비율 (%)", 10, 300, 100, help="10% 미만은 데이터 오류 방지를 위해 제외")
    set_ocf_ni = st.checkbox("OCF > NI 검증 (이익의 질)", value=True)
    set_fcf = st.checkbox("FCF 발생 여부 (현금 잉여)", value=True)

    st.divider()
    start_scan = st.button("📊 검색 시작", type="primary", use_container_width=True)

# 4. 분석 엔진
if start_scan:
    all_tickers = get_combined_tickers()
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, t in enumerate(all_tickers):
        status_text.text(f"분석 중: {t} ({i+1}/{len(all_tickers)})")
        progress_bar.progress((i + 1) / len(all_tickers))
        
        try:
            s = yf.Ticker(t)
            inf = s.info
            
            # 필수 데이터 검증 (데이터 누락 방지)
            equity = inf.get('totalStockholderEquity')
            shares = inf.get('sharesOutstanding')
            roe = inf.get('returnOnEquity')
            price = inf.get('currentPrice')
            
            if not all([equity, shares, roe, price]): continue

            # 지표 추출
            per = inf.get('trailingPE') or 0
            pbr = inf.get('priceToBook') or 0
            mkt_cap = inf.get('marketCap', 0) / 1e9
            total_debt = inf.get('totalDebt') or 0
            debt_ratio = (total_debt / equity) * 100
            op_margin = (inf.get('operatingMargins') or 0) * 100
            ocf = inf.get('operatingCashflow') or 0
            ni = inf.get('netIncomeToCommon') or 0
            fcf = inf.get('freeCashflow') or 0

            # --- 필터링 로직 ---
            if mkt_cap < set_mktcap: continue
            if roe < set_roe: continue
            if per <= 0 or per > set_per: continue
            if pbr <= 0 or pbr > set_pbr: continue
            # [수정] 부채비율 하한선 10% 조건 추가
            if debt_ratio < 10 or debt_ratio > set_debt: continue
            if op_margin < (10 + set_op_margin): continue
            if set_ocf_ni and ocf <= ni: continue
            if set_fcf and fcf <= 0: continue

            # RIM 적정가 산출
            # $$기업가치 = 자기자본 + \frac{자기자본 \times (ROE - r)}{r}$$
            ent_value = equity + (equity * (roe - set_exp_return) / set_exp_return)
            fair_price = ent_value / shares
            margin = ((fair_price / price) - 1) * 100
            
            # 10% 미만 마진 제외
            if margin < set_buy_margin: continue

            results.append({
                "신호": "🟢 매수", "티커": t, "기업명": inf.get('shortName'),
                "안전마진": f"{margin:.1f}%", "현재가": f"${price:.2f}",
                "적정가": f"${fair_price:.2f}", "ROE": f"{roe:.1%}",
                "부채비율": f"{debt_ratio:.1f}%", "이익질": "✅ 우수",
                "raw_margin": margin
            })
        except: continue
    
    st.session_state['f_data'] = pd.DataFrame(results)
    st.session_state['searched'] = True

# 5. 결과 출력
if st.session_state.get('searched'):
    df = st.session_state['f_data']
    if not df.empty:
        st.subheader(f"✅ 회계 원칙을 준수하는 {len(df)}개 종목 발견")
        st.dataframe(df.sort_values('raw_margin', ascending=False).drop('raw_margin', axis=1), use_container_width=True)
    else:
        st.error("❌ 현재 시장에서 부채비율 10% 이상 및 안전 마진 10% 이상인 초우량주가 없습니다. 설정을 미세 조정해보세요.")
