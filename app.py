import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import requests
import io

# 1. 페이지 설정
st.set_page_config(page_title="US Quant Terminal v14", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #000000; }
    .main-title { color: #0f172a; font-size: 28px; font-weight: 800; text-align: center; padding: 15px; border-bottom: 2px solid #f1f5f9; }
    .sidebar-title { color: #2563eb; font-size: 17px; font-weight: 800; margin-top: 15px; }
    .status-pass { color: #22c55e; font-weight: bold; }
    .status-fail { color: #ef4444; font-weight: bold; }
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

# 3. 사이드바 모드 및 8대 필터 배치
with st.sidebar:
    st.markdown('<div class="sidebar-title">🖥️ 분석 모드 선택</div>', unsafe_allow_html=True)
    mode = st.radio("모드", ["📊 회계 우량주 (Buffett)", "🔍 일반 우량주 (v2)"])
    st.divider()

    if mode == "📊 회계 우량주 (Buffett)":
        st.markdown("### 📌 공통/수익성")
        set_mktcap = st.number_input("최소 시총 ($B)", value=2.0, help="소형주 제외")
        set_roe = st.slider("최소 ROE (%)", 0, 50, 10, help="자본 효율성") / 100
        set_op_margin = st.slider("영업이익률 가점 (%)", 0, 30, 0, help="업종 평균 대비 초과수익")
        
        st.markdown("### ⚖️ 가치평가 (RIM)")
        set_exp_return = st.number_input("기대수익률 (r, %)", value=5.5, help="낮을수록 적정가 상승") / 100
        set_buy_margin = st.slider("매수 신호 기준 (%)", 10, 50, 10, help="최소 안전마진 하한선")
        
        st.markdown("### 🛡️ 재무건전성")
        set_debt = st.slider("최대 부채비율 (%)", 10, 300, 150, help="10% 미만 데이터 오류 방지")
        set_ocf_ni = st.checkbox("OCF > NI 검증", value=False, help="이익의 질 확인")
    else:
        st.markdown("### ⚙️ 일반 투자 필터")
        max_per = st.slider("최대 PER", 1, 100, 30)
        min_roe = st.slider("최소 ROE (%)", 0, 50, 12) / 100
        max_pbr = st.slider("최대 PBR", 0.1, 15.0, 5.0)
        filter_ebitda = st.checkbox("EBITDA 성장 필수", value=False)

    start_scan = st.button("🚀 분석 시작", type="primary", use_container_width=True)

# 4. 분석 엔진 및 데이터 처리
if start_scan:
    all_tickers = get_combined_tickers()
    results = []
    progress = st.progress(0); status = st.empty()

    for i, t in enumerate(all_tickers):
        status.text(f"분석 중: {t}")
        progress.progress((i + 1) / len(all_tickers))
        try:
            s = yf.Ticker(t); inf = s.info
            price = inf.get('currentPrice', 0); roe = inf.get('returnOnEquity', 0)
            
            if mode == "📊 회계 우량주 (Buffett)":
                equity = inf.get('totalStockholderEquity'); shares = inf.get('sharesOutstanding')
                if not all([equity, shares, roe, price]): continue
                debt_r = ((inf.get('totalDebt') or 0) / equity) * 100
                if debt_r < 10 or debt_r > set_debt or roe < set_roe: continue
                
                # RIM 계산
                ent_v = equity + (equity * (roe - set_exp_return) / set_exp_return)
                fair_p = ent_v / shares; margin = ((fair_p / price) - 1) * 100
                if margin < set_buy_margin: continue
                
                results.append({"티커": t, "기업명": inf.get('shortName'), "현재가": f"${price:.2f}", "적정가": f"${fair_p:.2f}", "안전마진": f"{margin:.1f}%", "ROE": f"{roe:.1%}", "부채비율": f"{debt_r:.1f}%", "raw_margin": margin})
            
            else: # v2 모드
                pe = inf.get('trailingPE', 0); pbr = inf.get('priceToBook', 0)
                if 0 < pe <= max_per and roe >= min_roe and 0 < pbr <= max_pbr:
                    raw_y = inf.get('trailingAnnualDividendYield') or inf.get('dividendYield') or 0
                    results.append({"티커": t, "기업명": inf.get('shortName'), "현재가": f"${price:.2f}", "PER": round(pe, 1), "ROE": f"{roe:.1%}", "배당률": f"{raw_y:.2%}", "raw_margin": roe})
        except: continue

    st.session_state['scan_results'] = pd.DataFrame(results)

# 5. 결과 대시보드 (상세 리포트 포함)
if 'scan_results' in st.session_state:
    df = st.session_state['scan_results']
    if not df.empty:
        st.markdown('<div class="main-title">🚦 분석 결과 및 정밀 리포트</div>', unsafe_allow_html=True)
        st.dataframe(df.sort_values('raw_margin', ascending=False).drop(columns=['raw_margin']), use_container_width=True)

        st.divider()
        selected = st.selectbox("🎯 상세 분석 종목 선택", df['티커'].tolist())
        
        if selected:
            s_obj = yf.Ticker(selected); s_inf = s_obj.info
            
            # 메트릭 카드
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("현재가", f"${s_inf.get('currentPrice')}")
            c2.metric("배당률", f"{(s_inf.get('dividendYield', 0)*100):.2f}%")
            c3.metric("ROE", f"{(s_inf.get('returnOnEquity', 0)*100):.1f}%")
            c4.metric("시가총액", f"${(s_inf.get('marketCap', 0)/1e9):.1f}B")

            # 차트 및 배당 기록
            col_l, col_r = st.columns([2, 1])
            with col_l:
                st.write("📈 **1년 주가 흐름 (캔들스틱)**")
                h = s_obj.history(period="1y")
                fig = go.Figure(data=[go.Candlestick(x=h.index, open=h['Open'], high=h['High'], low=h['Low'], close=h['Close'])])
                st.plotly_chart(fig, use_container_width=True)
            with col_r:
                st.write("📅 **배당 지급 기록**")
                if not s_obj.dividends.empty: st.bar_chart(s_obj.dividends.tail(10))
                else: st.info("배당 기록 없음")
                
                st.write("🛡️ **회계 건전성 체크**")
                ocf = s_inf.get('operatingCashflow', 0); ni = s_inf.get('netIncomeToCommon', 0)
                st.write(f"OCF > NI: {'✅ 적합' if ocf > ni else '❌ 부적합'}")
                st.write(f"부채비율: {(s_inf.get('totalDebt', 0)/s_inf.get('totalStockholderEquity', 1)*100):.1f}%")
    else:
        st.error("❌ 조건에 맞는 종목이 없습니다. 필터를 조정해 보세요.")
