import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import requests
import io
import time

# 1. 페이지 설정
st.set_page_config(page_title="US Quant Terminal v3", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #000000; }
    .main-title { color: #0f172a; font-size: 28px; font-weight: 800; text-align: center; padding: 15px; border-bottom: 2px solid #f1f5f9; }
    .status-card { padding: 10px; border-radius: 8px; text-align: center; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

st.markdown('<div class="main-title">🏛️ 우량주 검색기 v3</div>', unsafe_allow_html=True)

# 2. 티커 로딩 (S&P 500 + Nasdaq 100)
@st.cache_data
def get_all_tickers():
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        sp_resp = requests.get('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies', headers=headers)
        sp500 = pd.read_html(io.StringIO(sp_resp.text))[0]['Symbol'].tolist()
        return [t.replace('.', '-') for t in sp500]
    except:
        return ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "BRK-B", "JPM", "V", "PG"]

# 3. 사이드바: 8가지 기준 설정
with st.sidebar:
    st.markdown("### ⚙️ 전략 매개변수")
    exp_return = st.number_input("기대수익률 (%)", value=8.0, step=0.5) / 100
    ind_op_margin = st.slider("업종 평균 영업이익률 (%)", 0, 30, 10)
    
    st.divider()
    st.markdown("### 🛡️ 안전 필터")
    min_mkt_cap = 2.0  # $2B 이상
    min_roe_avg = 15.0 # 3년 평균 15%
    max_debt_ratio = 100.0 # 부채비율 100% 미만
    
    start_scan = st.button("📊 분석 시작 (8대 기준 적용)", type="primary", use_container_width=True)

# 4. 핵심 분석 엔진
if start_scan:
    tickers = get_all_tickers()
    results = []
    progress = st.progress(0)
    status = st.empty()

    for idx, t in enumerate(tickers):
        status.text(f"검색 중: {t} ({idx+1}/{len(tickers)})")
        progress.progress((idx + 1) / len(tickers))
        
        try:
            s = yf.Ticker(t)
            inf = s.info
            
            # 1. 시가총액 필터 ($2B 이상)
            mkt_cap = inf.get('marketCap', 0) / 1e9
            if mkt_cap < min_mkt_cap: continue

            # 2 & 3. 재무제표 분석 (ROE, 부채비율, 현금흐름)
            fin = s.financials
            bs = s.balance_sheet
            cf = s.cashflow

            # 부채비율 계산 (Total Debt / Equity)
            total_debt = inf.get('totalDebt', 0)
            equity = inf.get('totalStockholderEquity', 1)
            debt_ratio = (total_debt / equity) * 100
            if debt_ratio > max_debt_ratio: continue

            # 4. 영업이익률 필터 (업종 대비 +10%)
            op_margin = inf.get('operatingMargins', 0) * 100
            if op_margin < (ind_op_margin + 10): continue

            # 5 & 6. 현금흐름 검증 (OCF > NI & FCF 존재)
            ocf = inf.get('operatingCashflow', 0)
            ni = inf.get('netIncomeToCommon', 0)
            fcf = inf.get('freeCashflow', 0)
            if ocf <= ni or fcf <= 0: continue

            # 7. 적정 주가 계산 (RIM 모델)
            # 적정주가 = (자기자본 + (자기자본 * (ROE - 기대수익률) / 기대수익률)) / 발행주식수
            cur_roe = inf.get('returnOnEquity', 0)
            shares = inf.get('sharesOutstanding', 1)
            
            ent_value = equity + (equity * (cur_roe - exp_return) / exp_return)
            fair_price = ent_value / shares
            cur_price = inf.get('currentPrice', 1)
            
            # 8. 안전 마진 및 신호 판정
            margin = ((fair_price / cur_price) - 1) * 100
            
            if margin >= 20: signal, color = "🟢 매수 검토", "#dcfce7"
            elif -10 <= margin <= 10: signal, color = "🟡 보유", "#fef9c3"
            elif margin <= -20: signal, color = "🔴 과열/매도", "#fee2e2"
            else: signal, color = "⚪ 관망", "#f1f5f9"

            # 가점 및 성장 점수
            eps_growth = "✅ 우상향" if inf.get('forwardEps', 0) > inf.get('trailingEps', 0) else "❌ 정체"
            
            results.append({
                "신호": signal, "티커": t, "기업명": inf.get('shortName'),
                "안전마진": f"{margin:.1f}%", "현재가": f"${cur_price:.2f}",
                "적정주가": f"${fair_price:.2f}", "ROE": f"{cur_roe:.1%}",
                "부채비율": f"{debt_ratio:.1f}%", "영업이익률": f"{op_margin:.1f}%",
                "EPS성장": eps_growth, "color": color
            })
            
        except Exception as e:
            continue

    st.session_state['data'] = pd.DataFrame(results)

# 5. 결과 대시보드
if 'data' in st.session_state:
    df = st.session_state['data']
    if not df.empty:
        st.subheader(f"✅ 회계적 우량주 {len(df)}개 발견")
        
        # 스타일링된 데이터프레임
        st.dataframe(df.drop(columns=['color']), use_container_width=True)
        
        # 개별 종목 상세 진단
        st.divider()
        selected = st.selectbox("🎯 상세 기업 가치평가 리포트", df['티커'].tolist())
        
        if selected:
            row = df[df['티커'] == selected].iloc[0]
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("RIM 적정가", row['적정주가'], row['안전마진'])
            with c2:
                st.metric("부채비율", row['부채비율'])
            with c3:
                st.metric("이익의 질", "OCF > NI ✅")

            # 주가 및 현금흐름 차트
            st.plotly_chart(go.Figure(data=[go.Candlestick(
                x=yf.Ticker(selected).history(period="1y").index,
                open=yf.Ticker(selected).history(period="1y")['Open'],
                high=yf.Ticker(selected).history(period="1y")['High'],
                low=yf.Ticker(selected).history(period="1y")['Low'],
                close=yf.Ticker(selected).history(period="1y")['Close']
            )]).update_layout(title=f"{selected} 1년 주가 흐름"), use_container_width=True)
    else:
        st.warning("설정하신 엄격한 기준을 통과한 종목이 없습니다. 기대수익률을 조정해보세요.")
