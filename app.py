import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import requests
import io

# 1. 페이지 설정
st.set_page_config(page_title="US Quant Terminal v5", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #000000; }
    .main-title { color: #0f172a; font-size: 28px; font-weight: 800; text-align: center; padding: 15px; border-bottom: 2px solid #f1f5f9; }
    .sidebar-title { color: #1e293b; font-size: 16px; font-weight: 700; margin-top: 10px; }
    </style>
    """, unsafe_allow_html=True)

st.markdown('<div class="main-title">🏛️ 우량주 검색기</div>', unsafe_allow_html=True)

# 2. 종목 리스트 로딩
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

# 3. 사이드바: 8가지 필터 컨트롤러 (도움말 내장)
with st.sidebar:
    if st.button("🔄 설정 초기화", use_container_width=True):
        st.session_state.clear()
        st.rerun()
    
    st.divider()
    st.markdown('<div class="sidebar-title">📊 필터 설정</div>', unsafe_allow_html=True)
    
    # 필터 1: 시가총액
    set_mktcap = st.number_input(
        "1. 최소 시가총액 ($B)", 
        value=2.0, step=0.5,
        help="너무 작은 소형주 거르기."
    )
    # 필터 2: ROE
    set_roe = st.slider(
        "2. 최소 ROE (%)", 
        0, 50, 15,
        help="자본을 얼마나 효율적으로 사용하여 이익을 내는지 측정."
    ) / 100
    # 필터 3: 부채비율
    set_debt = st.slider(
        "3. 최대 부채비율 (%)", 
        10, 300, 100,
        help="재무 건전성을 확인합니다. 100% 미만은 자기자본이 부채보다 많다는 뜻."
    )
    # 필터 4: 영업이익률 프리미엄
    set_op_margin = st.slider(
        "4. 최소 영업이익률 가점 (%)", 
        0, 30, 10,
        help="단순히 이익이 나는 게 아니라, 업종 평균보다 얼마나 더 '독점적 지위'를 가졌는지 판단."
    )
    # 필터 5: OCF vs NI
    set_ocf_ni = st.checkbox(
        "5. OCF > NI 필수 검증", 
        value=True,
        help="장부상 이익보다 실제 현금 유입이 더 큰지 확인하여 분식회계나 부실 매출을 차단."
    )
    # 필터 6: FCF 존재여부
    set_fcf = st.checkbox(
        "6. 잉여현금흐름(FCF) 발생 필수", 
        value=True,
        help="배당을 주거나 재투자를 할 수 있는 실제 '잉여 현금'이 있는지 확인."
    )
    # 필터 7: 적정가 계산용 기대수익률
    set_exp_return = st.number_input(
        "7. RIM 기대수익률 (r, %)", 
        value=7.0, step=0.1,
        help="RIM 모델의 핵심 변수입니다. 시장에서 기대하는 최소 수익률을 입력."
    ) / 100
    # 필터 8: 안전 마진 매수 신호 기준
    set_buy_margin = st.slider(
        "8. 매수 검토(초록불) 기준 (%)", 
        10, 50, 20,
        help="안전 마진이 몇 % 이상일 때 초록불(매수 검토)을 켤지 정함."
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
            
            # 필수 데이터 누락 시 스킵 (데이터 무결성)
            equity = inf.get('totalStockholderEquity')
            shares = inf.get('sharesOutstanding')
            roe = inf.get('returnOnEquity')
            price = inf.get('currentPrice')
            
            if not all([equity, shares, roe, price]): continue

            # [필터 1] 시가총액
            mkt_cap = inf.get('marketCap', 0) / 1e9
            if mkt_cap < set_mktcap: continue

            # [필터 2] ROE
            if roe < set_roe: continue

            # [필터 3] 부채비율
            total_debt = inf.get('totalDebt') or 0
            debt_ratio = (total_debt / equity) * 100
            if debt_ratio > set_debt: continue

            # [필터 4] 영업이익률
            op_margin = (inf.get('operatingMargins') or 0) * 100
            if op_margin < (10 + set_op_margin): continue

            # [필터 5 & 6] 현금흐름 검증
            ocf = inf.get('operatingCashflow') or 0
            ni = inf.get('netIncomeToCommon') or 0
            fcf = inf.get('freeCashflow') or 0
            if set_ocf_ni and ocf <= ni: continue
            if set_fcf and fcf <= 0: continue

            # [필터 7] RIM 적정 주가 계산
            # RIM 공식: 기업가치 = 자기자본 + (자기자본 * (ROE - r) / r)
            ent_value = equity + (equity * (roe - set_exp_return) / set_exp_return)
            fair_price = ent_value / shares
            
            # [필터 8] 안전 마진 및 최종 신호
            margin = ((fair_price / price) - 1) * 100
            
            if margin >= set_buy_margin: signal = "🟢 매수 검토"
            elif -10 <= margin <= 10: signal = "🟡 보유"
            elif margin <= -20: signal = "🔴 과열/매도"
            else: signal = "⚪ 관망"

            # 가점 및 성장성
            eps_up = "✅" if (inf.get('forwardEps') or 0) > (inf.get('trailingEps') or 0) else "❌"

            results.append({
                "신호": signal, "티커": t, "기업명": inf.get('shortName'),
                "안전마진": f"{margin:.1f}%", "현재가": f"${price:.2f}",
                "적정가": f"${fair_price:.2f}", "ROE": f"{roe:.1%}",
                "부채비율": f"{debt_ratio:.1f}%", "OP이익률": f"{op_margin:.1f}%",
                "이익질": "✅ 우수", "EPS성장": eps_up, "raw_margin": margin
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
        selected = st.selectbox("🎯 상세 종목 가치 진단", df['티커'].tolist())
        if selected:
            s_obj = yf.Ticker(selected)
            sel_row = df[df['티커']==selected].iloc[0]
            
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.metric("RIM 적정가", sel_row['적정가'], sel_row['안전마진'])
            with c2: st.metric("현재가", sel_row['현재가'])
            with c3: st.metric("ROE", sel_row['ROE'])
            with c4: st.metric("부채비율", sel_row['부채비율'])
            
            st.plotly_chart(go.Figure(data=[go.Candlestick(
                x=s_obj.history(period="1y").index,
                open=s_obj.history(period="1y")['Open'],
                high=s_obj.history(period="1y")['High'],
                low=s_obj.history(period="1y")['Low'],
                close=s_obj.history(period="1y")['Close']
            )]).update_layout(title=f"{selected} 1년 주가 흐름", template="plotly_white", height=400), use_container_width=True)
    else:
        st.error("❌ 현재 기준을 모두 만족하는 종목이 없습니다. 필터를 완화해보세요.")
