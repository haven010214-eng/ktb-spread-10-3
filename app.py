"""국고채 10년-3년 스프레드 대시보드 (데이터: 한국은행 ECOS, 시장금리 일별 817Y002)."""

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots

# ── ECOS 설정 ────────────────────────────────────────────────
ECOS_URL = "https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/{n}/817Y002/D/{start}/{end}/{item}"
ITEMS = {"3Y": "010200000", "10Y": "010210000"}  # 국고채(3년), 국고채(10년)

PERIODS = {"1개월": 31, "3개월": 92, "6개월": 183, "1년": 366, "3년": 1096, "5년": 1827, "10년": 3653}

# ── 팔레트 ───────────────────────────────────────────────────
INK = "#14213D"
MUTED = "#5B6577"
GRID = "#DDE2EA"
STEEP = "#0F766E"   # 양(+) 스프레드
INVERT = "#B42318"  # 역전(-)
Y3 = "#7C8BA1"
Y10 = "#14213D"

st.set_page_config(page_title="국고채 10-3 스프레드", page_icon="📈", layout="wide")

st.markdown(
    f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600&display=swap');
html, body, [class*="css"], .stMarkdown, .stMetric {{
  font-family: 'IBM Plex Sans KR', 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif;
}}
.block-container {{ padding-top: 2rem; max-width: 1200px; }}
.hero {{ display:flex; align-items:flex-end; gap:2.5rem; flex-wrap:wrap; margin: .25rem 0 1.5rem; }}
.hero-num {{ font-size: clamp(3.5rem, 9vw, 6.5rem); font-weight:600; line-height:.95;
  letter-spacing:-0.03em; font-variant-numeric: tabular-nums; }}
.hero-num small {{ font-size:.32em; font-weight:500; margin-left:.15em; color:{MUTED}; letter-spacing:0; }}
.hero-side {{ padding-bottom:.5rem; color:{INK}; }}
.hero-side .state {{ font-size:1.15rem; font-weight:600; }}
.hero-side .sub {{ color:{MUTED}; font-size:.92rem; margin-top:.2rem; font-variant-numeric: tabular-nums; }}
.legs {{ display:flex; gap:2rem; flex-wrap:wrap; padding:.9rem 0; border-top:1px solid {GRID};
  border-bottom:1px solid {GRID}; margin-bottom:1.25rem; font-variant-numeric: tabular-nums; }}
.legs div {{ min-width:9rem; }}
.legs .k {{ color:{MUTED}; font-size:.85rem; }}
.legs .v {{ font-size:1.35rem; font-weight:600; color:{INK}; }}
.legs .d {{ font-size:.85rem; margin-left:.35rem; }}
</style>
""",
    unsafe_allow_html=True,
)


# ── 데이터 ───────────────────────────────────────────────────
class EcosError(Exception):
    pass


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_series(api_key: str, item: str, start: str, end: str) -> pd.Series:
    url = ECOS_URL.format(key=api_key, n=100000, start=start, end=end, item=item)
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        js = r.json()
    except requests.RequestException as e:
        raise EcosError(f"ECOS 서버에 연결하지 못했습니다: {e}") from e
    except ValueError as e:
        raise EcosError("ECOS 응답을 해석하지 못했습니다. API 키를 확인하세요.") from e

    if "RESULT" in js:  # 오류 응답
        code, msg = js["RESULT"].get("CODE", ""), js["RESULT"].get("MESSAGE", "")
        raise EcosError(f"ECOS {code}: {msg}")

    rows = js.get("StatisticSearch", {}).get("row", [])
    if not rows:
        raise EcosError("조회된 데이터가 없습니다.")
    s = pd.Series(
        {pd.to_datetime(r["TIME"], format="%Y%m%d"): float(r["DATA_VALUE"]) for r in rows if r.get("DATA_VALUE")},
        dtype=float,
    )
    return s.sort_index()


def load(api_key: str, days: int) -> pd.DataFrame:
    end = date.today()
    # 이동평균·52주 통계를 위해 여유분 1년 더 조회
    start = end - timedelta(days=days + 400)
    s, e = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    df = pd.concat(
        {k: fetch_series(api_key, v, s, e) for k, v in ITEMS.items()}, axis=1
    ).dropna()
    df["spread_bp"] = (df["10Y"] - df["3Y"]) * 100
    return df


def fmt_chg(x: float, unit: str = "bp", digits: int = 1) -> str:
    if pd.isna(x):
        return "–"
    color = STEEP if x > 0 else INVERT if x < 0 else MUTED
    return f'<span class="d" style="color:{color}">{x:+.{digits}f}{unit}</span>'


# ── 사이드바 ──────────────────────────────────────────────────
with st.sidebar:
    st.subheader("설정")
    try:
        secret_key = st.secrets["ECOS_API_KEY"]
    except Exception:
        secret_key = ""
    api_key = secret_key or st.text_input("ECOS API 키", type="password",
                                          help="ecos.bok.or.kr → Open API → 인증키 신청")
    period = st.radio("기간", list(PERIODS), index=3, horizontal=True)
    ma_win = st.select_slider("이동평균(영업일)", options=[0, 5, 20, 60, 120], value=20,
                              format_func=lambda x: "없음" if x == 0 else f"{x}일")
    if st.button("새로고침"):
        fetch_series.clear()
        st.rerun()
    st.caption("데이터: 한국은행 ECOS 시장금리(일별), 금융투자협회 최종호가수익률 기준. "
               "장중 실시간이 아닌 일별 종가이며 30분마다 캐시를 갱신합니다.")

st.markdown(f"<div style='color:{MUTED};font-size:.95rem'>국고채 10년 − 3년 스프레드</div>",
            unsafe_allow_html=True)

if not api_key:
    st.info("왼쪽 사이드바에 ECOS API 키를 입력하면 데이터를 불러옵니다. "
            "키는 한국은행 ECOS 홈페이지의 Open API 메뉴에서 무료로 발급받을 수 있습니다.")
    st.stop()

try:
    with st.spinner("ECOS에서 금리를 불러오는 중"):
        full = load(api_key, PERIODS[period])
except EcosError as e:
    st.error(str(e))
    st.stop()

if full.empty:
    st.warning("3년·10년 금리가 모두 있는 날짜가 없습니다. 기간을 늘려보세요.")
    st.stop()

if ma_win:
    full["ma"] = full["spread_bp"].rolling(ma_win).mean()
cutoff = full.index[-1] - pd.Timedelta(days=PERIODS[period])
df = full[full.index >= cutoff].copy()

# ── 헤드라인 ──────────────────────────────────────────────────
last, prev = full.iloc[-1], full.iloc[-2] if len(full) > 1 else full.iloc[-1]
d1 = last["spread_bp"] - prev["spread_bp"]


def chg_since(days: int) -> float:
    past = full[full.index <= full.index[-1] - pd.Timedelta(days=days)]
    return last["spread_bp"] - past["spread_bp"].iloc[-1] if len(past) else float("nan")


d1m = chg_since(30)
sp = last["spread_bp"]
if sp < 0:
    state, color = "역전", INVERT
elif d1 > 0:
    state, color = "스티프닝", STEEP
elif d1 < 0:
    state, color = "플래트닝", INK
else:
    state, color = "보합", INK

st.markdown(
    f"""
<div class="hero">
  <div class="hero-num" style="color:{color if sp < 0 else INK}">{sp:.1f}<small>bp</small></div>
  <div class="hero-side">
    <div class="state" style="color:{color}">{state}</div>
    <div class="sub">{full.index[-1]:%Y-%m-%d} 기준 · 전일 {fmt_chg(d1)} · 1개월 {fmt_chg(d1m)}</div>
  </div>
</div>
<div class="legs">
  <div><div class="k">국고 3년</div><span class="v">{last['3Y']:.3f}%</span>{fmt_chg((last['3Y']-prev['3Y'])*100)}</div>
  <div><div class="k">국고 10년</div><span class="v">{last['10Y']:.3f}%</span>{fmt_chg((last['10Y']-prev['10Y'])*100)}</div>
  <div><div class="k">{period} 평균</div><span class="v">{df['spread_bp'].mean():.1f}bp</span></div>
  <div><div class="k">{period} 범위</div><span class="v">{df['spread_bp'].min():.1f} ~ {df['spread_bp'].max():.1f}</span></div>
  <div><div class="k">{period} 내 백분위</div><span class="v">{(df['spread_bp'] <= sp).mean()*100:.0f}%</span></div>
  <div><div class="k">Z-score</div><span class="v">{(sp - df['spread_bp'].mean()) / (df['spread_bp'].std() or 1):+.2f}</span></div>
</div>
""",
    unsafe_allow_html=True,
)

# ── 차트 ─────────────────────────────────────────────────────
fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.62, 0.38], vertical_spacing=0.06)

pos = df["spread_bp"].clip(lower=0)
neg = df["spread_bp"].clip(upper=0)
fig.add_trace(go.Scatter(x=df.index, y=pos, fill="tozeroy", mode="none",
                         fillcolor="rgba(15,118,110,0.14)", hoverinfo="skip", showlegend=False), 1, 1)
fig.add_trace(go.Scatter(x=df.index, y=neg, fill="tozeroy", mode="none",
                         fillcolor="rgba(180,35,24,0.16)", hoverinfo="skip", showlegend=False), 1, 1)
fig.add_trace(go.Scatter(x=df.index, y=df["spread_bp"], name="10-3 스프레드",
                         line=dict(color=INK, width=1.8),
                         hovertemplate="%{x|%Y-%m-%d}<br>%{y:.1f}bp<extra></extra>"), 1, 1)
if ma_win:
    fig.add_trace(go.Scatter(x=df.index, y=df["ma"], name=f"{ma_win}일 이동평균",
                             line=dict(color=STEEP, width=1.2, dash="dot"),
                             hovertemplate="%{y:.1f}bp<extra>MA</extra>"), 1, 1)
fig.add_hline(y=0, line=dict(color=INVERT, width=1), row=1, col=1)

fig.add_trace(go.Scatter(x=df.index, y=df["3Y"], name="국고 3년", line=dict(color=Y3, width=1.5),
                         hovertemplate="%{y:.3f}%<extra>3Y</extra>"), 2, 1)
fig.add_trace(go.Scatter(x=df.index, y=df["10Y"], name="국고 10년", line=dict(color=Y10, width=1.5),
                         hovertemplate="%{y:.3f}%<extra>10Y</extra>"), 2, 1)

fig.update_layout(
    height=620, margin=dict(l=10, r=10, t=10, b=10), hovermode="x unified",
    plot_bgcolor="white", paper_bgcolor="white",
    font=dict(family="IBM Plex Sans KR, sans-serif", color=INK, size=12),
    legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0),
)
fig.update_xaxes(showgrid=False, linecolor=GRID)
fig.update_yaxes(gridcolor=GRID, zeroline=False)
fig.update_yaxes(title_text="bp", row=1, col=1)
fig.update_yaxes(title_text="%", row=2, col=1)
st.plotly_chart(fig, width="stretch")

# ── 테이블 ───────────────────────────────────────────────────
with st.expander("일별 데이터"):
    out = df[["3Y", "10Y", "spread_bp"]].sort_index(ascending=False).copy()
    out["전일대비(bp)"] = out["spread_bp"].diff(-1)
    out.index = out.index.strftime("%Y-%m-%d")
    out.index.name = "일자"
    out.columns = ["국고 3년(%)", "국고 10년(%)", "스프레드(bp)", "전일대비(bp)"]
    st.dataframe(out.style.format("{:.3f}", subset=["국고 3년(%)", "국고 10년(%)"])
                 .format("{:+.1f}", subset=["전일대비(bp)"], na_rep="–")
                 .format("{:.1f}", subset=["스프레드(bp)"]),
                 width="stretch", height=360)
    st.download_button("CSV로 저장", out.to_csv().encode("utf-8-sig"),
                       file_name=f"ktb_10y3y_spread_{date.today():%Y%m%d}.csv", mime="text/csv")
