import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import requests
import io

# 1. 페이지 설정
st.set_page_config(page_title="US Quant Terminal v7", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #000000; }
    .main-title { color: #0f172a; font-size: 28px; font-weight: 800; text-align: center; padding: 15px; border-bottom: 2px solid #f1f5f9; }
    .sidebar-title { color: #1e293b; font-size: 17px; font-weight: 800; margin-top: 15px; margin-bottom: 5px; color: #2563eb; }
    .filter-label { font-size: 14px; font-weight: 600; color: #475569; }
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

# 3. 사이드바: 4대 카테고리 필터 배치
with st.sidebar:
    if st.button("🔄 모든 설정 초기화", use_container_width=True):
        st.session_state.clear()
        st.rerun()
    
    st.divider()

    # --- 카테고리 1: 공통 설정 ---
    st.markdown('<div class="sidebar-title">📌 1. 공통 필터</div>', unsafe_allow_html=True)
    set_mktcap = st.number_input(
        "최소 시가총액 ($B)", value=2.0, step=0.5,
        help="너무 작은 소형주를 걸러내어 변동성을 줄이고 유동성을 확보합니다."
    )

    # --- 카테고리 2: 수익성 평가 ---
    st.markdown('<div class="sidebar-title">💰 2. 수익성 평가</div>', unsafe_allow_html=True)
    set_roe = st.slider(
        "최소 ROE (%)", 0, 50, 15,
        help="자기자본을 투입해 얼마나 효율적으로 순이익을 창출하는지 측정하는 핵심 지표입니다."
    ) / 100
    set_op_margin = st.slider(
        "영업이익률 가점 (%)", 0, 30, 10,
        help="단순 이익이 아닌, 업종 평균보다 높은 영업이익률로 경제적 해자(독점력)가 있는지 확인합니다."
    )

    # --- 카테고리 3: 가치 평가 ---
    st.markdown('<div class="sidebar-title">⚖️ 3. 가치 평가</div>', unsafe_allow_html=True)
    set_per = st.slider(
        "최대 PER (배)", 1.0, 100.0, 30.0,
        help="주가가 순이익 대비 몇 배인지 측정합니다. 낮을수록 저평가이나 업종별 차이가 있습니다."
    )
    set_pbr = st.slider(
        "최대 PBR (배)", 0.1, 15.0, 5.0,
        help="주가가 장부상 순자산 대비 몇 배인지 측정합니다. 자산 가치 대비 가격을 평가합니다."
    )
    set_exp_return = st.number_input(
        "RIM 기대수익률 (r, %)", value=7.0, step=0.1,
        help="적정 주가 계산 시 분모에 들어가는 요구수익률입니다. 높게 잡을수록 보수적인 평가가 됩니다."
    ) / 100
    set_buy_margin = st.slider(
        "매수 신호 기준 (%)", 10, 50, 20,
        help="적정가 대비 현재가가 몇 % 이상 저렴할 때 초록불(매수) 신호를 켤지 정합니다."
    )

    # --- 카테고리 4: 재무 건전성 ---
    st.markdown('<div class="sidebar-title">🛡️ 4. 재무 건전성</div>', unsafe_allow_html=True)
    set_debt = st.slider(
        "최대 부채비율 (%)", 10, 300, 100,
        help="기업의 타인자본 의존도를 나타냅니다. 100% 미만은 재무적으로 매우 안전함을 뜻합니다."
    )
    set_ocf_ni = st.checkbox(
        "OCF > NI 검증", value=True,
        help="영업활동현금흐름이 당기순이익보다 커야 장부상 이익이 아닌 실제 현금 유입으로 간주합니다."
    )
    set_fcf = st.checkbox(
        "FCF 발생 여부", value=True,
        help="잉여현금흐름이 (+)여야 주주 배당이나 부채 상환, 재투자가 가능합니다."
    )

    st.divider()
    start_scan = st.button("📊 검색 시작", type="primary", use_container_width=True)

# 4. 분석 로직
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

            # --- 필터링 로직 적용 ---
            if mkt_cap < set_mktcap: continue
            if roe < set_roe: continue
            if per <= 0 or per > set_per: continue
            if pbr <= 0 or pbr > set_pbr: continue
            if debt_ratio > set_debt: continue
            if op_margin < (10 + set_op_margin): continue
            if set_ocf_ni and ocf <= ni: continue
            if set_fcf and fcf <= 0: continue

            # 적정가 산출 (RIM)
            ent_value = equity + (equity * (roe - set_exp_return) / set_exp_return)
            fair_price = ent_value / shares
            margin = ((fair_price / price) - 1) * 100
            
            if margin >= set_buy_margin: signal = "🟢 매수"
            elif -10 <= margin <= 10: signal = "🟡 보유"
            elif margin <= -20: signal = "🔴 매도"
            else: signal = "⚪ 관망"

            results.append({
                "신호": signal, "티커": t, "기업명": inf.get('shortName'),
                "안전마진": f"{margin:.1f}%", "현재가": f"${price:.2f}",
                "적정가": f"${fair_price:.2f}", "ROE": f"{roe:.1%}",
                "PER": f"{per:.1f}배", "PBR": f"{pbr:.2f}배",
                "부채비율": f"{debt_ratio:.1f}%", "이익질": "✅" if ocf > ni else "❌",
                "raw_margin": margin
            })
        except: continue
    
    st.session_state['f_data'] = pd.DataFrame(results)
    st.session_state['searched'] = True

# 5. 결과 대시보드
if st.session_state.get('searched'):
    df = st.session_state['f_data']
    if not df.empty:
        st.subheader(f"✅ 필터링 결과: {len(df)}개 종목 발견")
        df = df.sort_values('raw_margin', ascending=False).drop('raw_margin', axis=1)
        st.dataframe(df, use_container_width=True)
        
        st.divider()
        selected = st.selectbox("🎯 상세 종목 진단", df['티커'].tolist())
        if selected:
            s_obj = yf.Ticker(selected)
            sel_row = df[df['티커']==selected].iloc[0]
            
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.metric("RIM 적정가", sel_row['적정가'], sel_row['안전마진'])
            with c2: st.metric("현재가", sel_row['현재가'])
            with c3: st.metric("가치 (PER/PBR)", f"{sel_row['PER']} / {sel_row['PBR']}")
            with c4: st.metric("건전성 (부채/이익질)", f"{sel_row['부채비율']} / {sel_row['이익질']}")
            
            st.plotly_chart(go.Figure(data=[go.Candlestick(
                x=s_obj.history(period="1y").index,
                open=s_obj.history(period="1y")['Open'],
                high=s_obj.history(period="1y")['High'],
                low=s_obj.history(period="1y")['Low'],
                close=s_obj.history(period="1y")['Close']
            )]).update_layout(title=f"{selected} 1년 주가 차트", template="plotly_white", height=400), use_container_width=True)
    else:
        st.error("❌ 현재 기준을 모두 만족하는 종목이 없습니다. 필터를 조정해보세요.")
