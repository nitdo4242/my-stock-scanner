import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import requests
import io

# 1. 페이지 설정
st.set_page_config(page_title="US Quant Terminal v10", layout="wide")

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

# 3. 사이드바: 필터 컨트롤러 (하한선 0으로 전면 개방)
with st.sidebar:
    if st.button("🔄 모든 설정 초기화", use_container_width=True):
        st.session_state.clear()
        st.rerun()
    
    st.divider()

    # --- 1. 공통 필터 ---
    st.markdown('<div class="sidebar-title">📌 1. 공통 필터</div>', unsafe_allow_html=True)
    set_mktcap = st.number_input("최소 시가총액 ($B)", value=2.0, step=0.5, help="소형주 제외")

    # --- 2. 수익성 평가 ---
    st.markdown('<div class="sidebar-title">💰 2. 수익성 평가</div>', unsafe_allow_html=True)
    set_roe = st.slider("최소 ROE (%)", 0, 50, 10, help="자본 효율성 (10~15% 권장)") / 100
    set_op_margin = st.slider("영업이익률 가점 (%)", 0, 30, 0, help="0% 설정 시 이익만 나면 통과")

    # --- 3. 가치 평가 ---
    st.markdown('<div class="sidebar-title">⚖️ 3. 가치 평가</div>', unsafe_allow_html=True)
    set_per = st.slider("최대 PER (배)", 1.0, 150.0, 50.0, help="고성장주 포함을 위해 확장")
    set_pbr = st.slider("최대 PBR (배)", 0.1, 20.0, 10.0, help="자산 가치 대비 가격")
    set_exp_return = st.number_input("RIM 기대수익률 (r, %)", value=5.5, step=0.1, help="낮을수록 적정가가 올라가 마진이 확보됨") / 100
    # [사용자 요청 반영] 매수 신호 기준 하한선 0%
    set_buy_margin = st.slider("매수 신호 기준 (%)", 0, 50, 0, help="0% 설정 시 적정가 이상의 모든 종목 표시")

    # --- 4. 재무 건전성 ---
    st.markdown('<div class="sidebar-title">🛡️ 4. 재무 건전성</div>', unsafe_allow_html=True)
    # [사용자 요청 반영] 부채비율 하한선 없이 0부터 설정 가능
    set_debt = st.slider("최대 부채비율 (%)", 0, 300, 150, help="0 설정 시 무부채 기업만 검색")
    set_ocf_ni = st.checkbox("OCF > NI 검증 (이익의 질)", value=False) # 초기값 False로 변경하여 검색량 증대
    set_fcf = st.checkbox("FCF 발생 여부 (현금 잉여)", value=False) # 초기값 False로 변경하여 검색량 증대

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
            
            # 필수 데이터 확인
            equity = inf.get('totalStockholderEquity')
            shares = inf.get('sharesOutstanding')
            roe = inf.get('returnOnEquity')
            price = inf.get('currentPrice')
            
            if not all([equity, shares, roe, price]): continue

            # 지표 추출
            per = inf.get('trailingPE') or 0
            pbr = inf.get('priceToBook') or 0
            mkt_cap = (inf.get('marketCap') or 0) / 1e9
            total_debt = inf.get('totalDebt') or 0
            debt_ratio = (total_debt / equity) * 100 if equity > 0 else 0
            op_margin = (inf.get('operatingMargins') or 0) * 100
            ocf = inf.get('operatingCashflow') or 0
            ni = inf.get('netIncomeToCommon') or 0
            fcf = inf.get('freeCashflow') or 0

            # --- 필터링 로직 ---
            if mkt_cap < set_mktcap: continue
            if roe < set_roe: continue
            # PER/PBR이 0인 경우는 데이터 누락으로 간주하여 제외 (필터값 보다는 작아야 함)
            if per > set_per or pbr > set_pbr: continue
            # 부채비율 0~설정값 사이 허용
            if debt_ratio > set_debt: continue
            if op_margin < (10 + set_op_margin): continue
            if set_ocf_ni and ocf <= ni: continue
            if set_fcf and fcf <= 0: continue

            # RIM 적정가 산출
            ent_value = equity + (equity * (roe - set_exp_return) / set_exp_return)
            fair_price = ent_value / shares
            margin = ((fair_price / price) - 1) * 100
            
            # 설정한 매수 신호 기준(0% 이상 등) 만족 시 포함
            if margin < set_buy_margin: continue

            results.append({
                "신호": "🟢 매수" if margin >= 10 else "🟡 보유",
                "티커": t, "기업명": inf.get('shortName'),
                "안전마진": f"{margin:.1f}%", "현재가": f"${price:.2f}",
                "적정가": f"${fair_price:.2f}", "ROE": f"{roe:.1%}",
                "부채비율": f"{debt_ratio:.1f}%", "PER": f"{per:.1f}배",
                "raw_margin": margin
            })
        except: continue
    
    st.session_state['f_data'] = pd.DataFrame(results)
    st.session_state['searched'] = True

# 5. 결과 출력
if st.session_state.get('searched'):
    df = st.session_state['f_data']
    if not df.empty:
        st.subheader(f"✅ 조건 만족 종목: {len(df)}개 발견")
        st.dataframe(df.sort_values('raw_margin', ascending=False).drop('raw_margin', axis=1), use_container_width=True)
    else:
        st.error("❌ 종목이 없습니다. [기대수익률을 5.0%]로 낮추고 [건전성 체크박스]를 모두 해제한 후 다시 시도해보세요.")
