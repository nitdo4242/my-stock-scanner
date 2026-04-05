import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import requests
import io

# 1. 페이지 설정 및 디자인
st.set_page_config(page_title="US Quant Terminal v2", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF !important; color: #000000 !important; }
    .main-title { color: #0f172a !important; font-size: 30px !important; font-weight: 800 !important; text-align: center; padding: 20px; border-bottom: 2px solid #f1f5f9; }
    .sidebar-title { color: #1e293b !important; font-size: 18px !important; font-weight: 700 !important; }
    [data-testid="stMetric"] { background-color: #f8fafc !important; border: 1px solid #e2e8f0 !important; border-radius: 8px !important; }
    </style>
    """, unsafe_allow_html=True)

st.markdown('<div class="main-title">🏛️ 우량주 검색기</div>', unsafe_allow_html=True)

# 2. 종목 리스트 로딩 (캐싱)
@st.cache_data
def get_all_tickers():
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        sp_resp = requests.get('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies', headers=headers)
        sp500 = pd.read_html(io.StringIO(sp_resp.text))[0]['Symbol'].tolist()
        nas_resp = requests.get('https://en.wikipedia.org/wiki/Nasdaq-100', headers=headers)
        nasdaq100 = pd.read_html(io.StringIO(nas_resp.text))[4]['Ticker'].tolist()
        combined = list(set(sp500 + nasdaq100))
        return [t.replace('.', '-') for t in combined]
    except:
        return ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "JPM", "V", "PG", "JNJ", "KO"]

# 3. 사이드바 구성
with st.sidebar:
    if st.button("🔄 필터 및 결과 초기화", use_container_width=True):
        for key in st.session_state.keys(): del st.session_state[key]
        st.rerun()
    
    st.divider()
    st.markdown('<div class="sidebar-title">⚙️ 투자 필터 설정</div>', unsafe_allow_html=True)
    max_per = st.slider("최대 PER", 1, 50, 28)
    min_roe = st.slider("최소 ROE (%)", 0, 50, 12) / 100
    max_pbr = st.slider("최대 PBR", 0.1, 5.0, 1.5)
    
    st.divider()
    filter_ebitda = st.checkbox("EBITDA 3년 연속 상승 필수", value=False)
    
    st.divider()
    start_scan = st.button("📊 검색 시작", type="primary", use_container_width=True)

# 4. 분석 로직
if start_scan:
    all_tickers = get_all_tickers()
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, t in enumerate(all_tickers):
        status_text.text(f"분석 중: {t} ({i+1}/{len(all_tickers)})")
        progress_bar.progress((i + 1) / len(all_tickers))
        try:
            s = yf.Ticker(t)
            inf = s.info
            
            # [수정] 배당률 정밀 추출 로직
            # 1순위: trailingAnnualDividendYield (과거 1년치 실제 배당률)
            # 2순위: dividendYield (현재 기준 배당률)
            # 3순위: dividendRate / currentPrice (직접 계산)
            raw_yield = inf.get('trailingAnnualDividendYield') or inf.get('dividendYield')
            cur_price = inf.get('currentPrice', 0)
            
            if (raw_yield is None or raw_yield == 0) and cur_price > 0:
                div_rate = inf.get('dividendRate', 0) or 0
                raw_yield = div_rate / cur_price if div_rate > 0 else 0
            
            # 소수점 오류 방지 (보통 0.015 형태로 들어옴)
            display_yield = raw_yield if raw_yield < 1 else raw_yield / 100
            
            # 기타 지표
            target_price = inf.get('targetMeanPrice', 0)
            pe = inf.get('trailingPE', 0)
            pbr = inf.get('priceToBook', 0)
            psr = inf.get('priceToSalesTrailing12Months', 0)
            roe = inf.get('returnOnEquity', 0)
            f_eps = inf.get('forwardEps', 0)
            t_eps = inf.get('trailingEps', 0)
            
            if 0 < pe <= max_per and roe >= min_roe and 0 < pbr <= max_pbr:
                # EBITDA 체크
                is_eb_growing = False
                income = s.income_stmt
                if 'EBITDA' in income.index:
                    ebs = income.loc['EBITDA']
                    if len(ebs) >= 3:
                        is_eb_growing = (ebs.iloc[0] > ebs.iloc[1] > ebs.iloc[2])
                
                if filter_ebitda and not is_eb_growing: continue
                
                # 안전 마진 및 신호 판정
                margin = 0
                if target_price > 0:
                    margin = ((target_price / cur_price) - 1) * 100
                
                if margin >= 20: signal = "🟢 매수 검토"
                elif -10 <= margin <= 10: signal = "🟡 보유"
                elif margin <= -20: signal = "🔴 과열/매도"
                else: signal = "⚪ 관망"

                results.append({
                    "신호": signal, "티커": t, "기업명": inf.get('shortName'),
                    "안전마진": f"{margin:.1f}%", "현재가": f"${cur_price}",
                    "배당률": f"{display_yield:.2%}", "PER": round(pe, 1),
                    "ROE": f"{roe:.1%}", "PBR": round(pbr, 2),
                    "PSR": round(psr, 2), "EPS성장": "✅ 우상향" if f_eps > t_eps else "❌ 정체",
                    "margin_val": margin
                })
        except: continue
    
    st.session_state['f_data'] = pd.DataFrame(results)
    st.session_state['searched'] = True

# 5. 결과 출력
if st.session_state.get('searched'):
    df = st.session_state['f_data']
    if not df.empty:
        st.write(f"### 🚦 시장 신호 리포트 ({len(df)}개 발견)")
        df['sort_val'] = df['신호'].map({"🟢 매수 검토": 0, "🟡 보유": 1, "⚪ 관망": 2, "🔴 과열/매도": 3})
        st.dataframe(df.sort_values('sort_val').drop(['sort_val', 'margin_val'], axis=1), use_container_width=True)
        
        st.divider()
        selected = st.selectbox("🎯 상세 종목 진단", df['티커'].tolist())
        if selected:
            s_obj = yf.Ticker(selected)
            s_inf = s_obj.info
            m1, m2, m3, m4 = st.columns(4)
            
            # 배당률 재계산 (상세창용)
            d_y = s_inf.get('trailingAnnualDividendYield') or s_inf.get('dividendYield', 0)
            if d_y > 1: d_y = d_y / 100
            
            m1.metric("안전 마진", f"{((s_inf.get('targetMeanPrice', 0)/s_inf.get('currentPrice', 1))-1)*100:.1f}%")
            m2.metric("현재가", f"${s_inf.get('currentPrice')}")
            m3.metric("PBR", f"{s_inf.get('priceToBook', 0):.2f}배")
            m4.metric("정밀 배당률", f"{d_y:.2%}")
            
            col_l, col_r = st.columns(2)
            with col_l:
                st.write("📅 **배당 지급 히스토리 (최근 12회)**")
                if not s_obj.dividends.empty: st.bar_chart(s_obj.dividends.tail(12), color="#10b981")
                else: st.info("배당 기록 없음")
            with col_r:
                st.write("📊 **주가 흐름 (1년)**")
                h_data = s_obj.history(period="1y")
                fig = go.Figure(data=[go.Candlestick(x=h_data.index, open=h_data['Open'], high=h_data['High'], low=h_data['Low'], close=h_data['Close'])])
                fig.update_layout(template="plotly_white", height=300, margin=dict(t=0, b=0, l=0, r=0))
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("❌ 조건에 맞는 종목이 없습니다. PBR 기준을 높여보세요.")
