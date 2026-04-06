import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import requests
import io

# 1. 페이지 설정
st.set_page_config(page_title="US Quant Terminal v3", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #000000; }
    .main-title { color: #0f172a; font-size: 28px; font-weight: 800; text-align: center; padding: 15px; border-bottom: 2px solid #f1f5f9; }
    .sidebar-title { color: #1e293b; font-size: 18px; font-weight: 700; }
    </style>
    """, unsafe_allow_html=True)

st.markdown('<div class="main-title">🏛️ 우량주 검색기 v3</div>', unsafe_allow_html=True)

# 2. 종목 리스트 로딩 (S&P 500 + 나스닥 100)
@st.cache_data
def get_combined_tickers():
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        # S&P 500
        sp_resp = requests.get('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies', headers=headers)
        sp500 = pd.read_html(io.StringIO(sp_resp.text))[0]['Symbol'].tolist()
        # 나스닥 100
        nas_resp = requests.get('https://en.wikipedia.org/wiki/Nasdaq-100', headers=headers)
        nasdaq100 = pd.read_html(io.StringIO(nas_resp.text))[4]['Ticker'].tolist()
        
        combined = list(set(sp500 + nasdaq100))
        return [t.replace('.', '-') for t in combined]
    except:
        return ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "AVGO", "PEP", "COST"]

# 3. 사이드바 구성
with st.sidebar:
    if st.button("🔄 필터 및 결과 초기화", use_container_width=True):
        st.session_state.clear()
        st.rerun()
    
    st.divider()
    st.markdown('<div class="sidebar-title">⚙️ 가치평가 및 필터 설정</div>', unsafe_allow_html=True)
    
    exp_return = st.number_input("기대수익률 (r, %)", value=7.0, step=0.5) / 100
    min_roe = st.slider("최소 ROE (%)", 0, 50, 15) / 100
    ind_op_margin = st.slider("업종 평균 영업이익률 (%)", 0, 30, 10)
    
    st.divider()
    st.markdown("### 🛡️ 8대 회계 기준 필터")
    filter_mktcap = st.checkbox("시가총액 $2B 이상", value=True)
    filter_debt = st.checkbox("부채비율 100% 미만", value=True)
    filter_ocf_ni = st.checkbox("영업현금흐름 > 당기순이익 (필수)", value=True)
    
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
            
            # [필수 데이터 체크] 데이터가 하나라도 없으면 계산 불가하므로 건너뜀 (이게 $0.00 방지 핵심)
            equity = inf.get('totalStockholderEquity')
            shares = inf.get('sharesOutstanding')
            cur_roe = inf.get('returnOnEquity')
            cur_price = inf.get('currentPrice')
            
            if not equity or not shares or not cur_roe or not cur_price:
                continue

            # 1. 시가총액 필터 ($2B 이상)
            mkt_cap = inf.get('marketCap', 0) / 1e9
            if filter_mktcap and mkt_cap < 2.0: continue

            # 2. ROE 필터 (설정값 이상)
            if cur_roe < min_roe: continue

            # 3. 부채비율 필터 (100% 미만)
            total_debt = inf.get('totalDebt') or 0
            debt_ratio = (total_debt / equity) * 100
            if filter_debt and debt_ratio > 100: continue

            # 4. 영업이익률 필터 (업종 대비 +10%)
            op_margin = (inf.get('operatingMargins') or 0) * 100
            if op_margin < (ind_op_margin + 10): continue

            # 5 & 6. 현금흐름 검증 (OCF > NI & FCF 존재)
            ocf = inf.get('operatingCashflow') or 0
            ni = inf.get('netIncomeToCommon') or 0
            fcf = inf.get('freeCashflow') or 0
            if filter_ocf_ni and (ocf <= ni or fcf <= 0): continue

            # 7. 적정 주가 계산 (RIM 모델)
            # 기업가치 = 자기자본 + (자기자본 * (ROE - 기대수익률) / 기대수익률)
            ent_value = equity + (equity * (cur_roe - exp_return) / exp_return)
            fair_price = ent_value / shares
            
            # 8. 안전 마진 및 신호 판정
            margin = ((fair_price / cur_price) - 1) * 100
            
            if margin >= 20: signal = "🟢 매수 검토"
            elif -10 <= margin <= 10: signal = "🟡 보유"
            elif margin <= -20: signal = "🔴 과열/매도"
            else: signal = "⚪ 관망"

            # EPS 성장성 체크
            eps_up = "✅ 우상향" if (inf.get('forwardEps') or 0) > (inf.get('trailingEps') or 0) else "❌ 정체"

            results.append({
                "신호": signal, "티커": t, "기업명": inf.get('shortName'),
                "안전마진": f"{margin:.1f}%", "현재가": f"${cur_price:.2f}",
                "적정주가": f"${fair_price:.2f}", "ROE": f"{cur_roe:.1%}",
                "부채비율": f"{debt_ratio:.1f}%", "영업이익률": f"{op_margin:.1f}%",
                "이익질(OCF>NI)": "✅ 우수", "EPS성장": eps_up,
                "raw_margin": margin
            })
        except:
            continue
    
    st.session_state['f_data'] = pd.DataFrame(results)
    st.session_state['searched'] = True

# 5. 결과 출력
if st.session_state.get('searched'):
    df = st.session_state['f_data']
    if not df.empty:
        st.write(f"### 🚦 시장 신호 리포트 ({len(df)}개 발견)")
        # 안전마진 높은 순으로 정렬
        display_df = df.sort_values('raw_margin', ascending=False).drop('raw_margin', axis=1)
        st.dataframe(display_df, use_container_width=True)
        
        st.divider()
        selected = st.selectbox("🎯 상세 종목 가치 진단", df['티커'].tolist())
        if selected:
            s_obj = yf.Ticker(selected)
            s_inf = s_obj.info
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("RIM 적정가", f"${df[df['티커']==selected]['적정주가'].values[0]}")
            c2.metric("현재가", f"${s_inf.get('currentPrice')}")
            c3.metric("부채비율", f"{df[df['티커']==selected]['부채비율'].values[0]}")
            c4.metric("ROE", f"{df[df['티커']==selected]['ROE'].values[0]}")
            
            # 주가 흐름 차트
            h_data = s_obj.history(period="1y")
            fig = go.Figure(data=[go.Candlestick(x=h_data.index, open=h_data['Open'], high=h_data['High'], low=h_data['Low'], close=h_data['Close'])])
            fig.update_layout(title=f"{selected} 1년 주가 흐름", template="plotly_white", height=400)
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("❌ 모든 기준(8대 필터)을 통과한 종목이 없습니다. 기대수익률을 낮추거나 필터를 조정해보세요.")
