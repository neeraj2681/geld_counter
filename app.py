"""
Real-time wealth counter.

Starts at INR 71,30,000 on a FIXED anchor date of 8 June 2026 (IST) and grows at
an assumed 10% per annum, compounded smoothly every second. Because the start
date is constant, the balance keeps continuing across days and sessions — it
never resets.

You can add or subtract a lump sum at any time. Each adjustment is applied at the
moment you click and, from that point onward, compounds at 10% along with the
rest of the balance. Adjustments are saved to disk so they persist too.

Pages
-----
• Home    — just the live money counter and the add/subtract controls.
• Charts  — growth-over-time line chart and a per-day "money generated" bar chart.
"""

import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st

PRINCIPAL = 7_130_000        # INR 71,30,000
ANNUAL_RATE = 0.10           # 10% per annum
SECONDS_PER_YEAR = 365.25 * 24 * 60 * 60

IST = ZoneInfo("Asia/Kolkata")
START_DT = datetime(2026, 6, 8, 0, 0, 0, tzinfo=IST)   # FIXED anchor — never resets

ADJ_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adjustments.json")


# ---------- persistence ----------
def load_adjustments() -> list:
    if not os.path.exists(ADJ_FILE):
        return []
    try:
        with open(ADJ_FILE) as f:
            raw = json.load(f)
        return [{"ts": datetime.fromisoformat(a["ts"]), "amount": float(a["amount"])} for a in raw]
    except Exception:
        return []


def save_adjustments(adjustments: list) -> None:
    data = [{"ts": a["ts"].isoformat(), "amount": a["amount"]} for a in adjustments]
    with open(ADJ_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ---------- helpers ----------
def format_inr(amount: float, decimals: int = 2) -> str:
    """Format a number with the Indian grouping system (e.g. 71,30,000.00)."""
    neg = amount < 0
    amount = abs(amount)
    whole = int(amount)
    frac = f"{amount - whole:.{decimals}f}"[2:]

    s = str(whole)
    if len(s) > 3:
        last3 = s[-3:]
        rest = s[:-3]
        parts = []
        while len(rest) > 2:
            parts.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            parts.insert(0, rest)
        grouped = ",".join(parts) + "," + last3
    else:
        grouped = s

    out = f"{grouped}.{frac}"
    return f"-{out}" if neg else out


def grow(amount: float, since: datetime, now: datetime) -> float:
    years = (now - since).total_seconds() / SECONDS_PER_YEAR
    return amount * (1 + ANNUAL_RATE) ** years


def value_at(t: datetime) -> float:
    """Value at time `t`: grown principal plus adjustments that happened by `t`."""
    total = grow(PRINCIPAL, START_DT, t)
    for adj in st.session_state.adjustments:
        if adj["ts"] <= t:
            total += grow(adj["amount"], adj["ts"], t)
    return total


def total_contributed() -> float:
    return PRINCIPAL + sum(adj["amount"] for adj in st.session_state.adjustments)


# ---------- shared state ----------
st.set_page_config(page_title="Wealth Counter", page_icon="💰", layout="centered")
if "adjustments" not in st.session_state:
    st.session_state.adjustments = load_adjustments()


def sidebar_details():
    with st.sidebar:
        st.header("Details")
        st.write(f"**Anchor date:** {START_DT.strftime('%d %b %Y')} (IST)")
        st.write(f"**Principal:** ₹{format_inr(PRINCIPAL)}")
        st.write(f"**Rate:** {ANNUAL_RATE * 100:.0f}% per annum")
        st.caption("Start date is fixed — the balance continues across days and never resets.")


# ==================== HOME PAGE (money only) ====================
def home_page():
    sidebar_details()
    st.title("💰 Live Wealth Counter")
    st.caption("Starting at ₹71,30,000 · assumed 10% per annum")

    # live counter
    @st.fragment(run_every=0.05)
    def counter():
        now = datetime.now(IST)
        value = value_at(now)
        gain = value - total_contributed()
        per_sec = value * ANNUAL_RATE / SECONDS_PER_YEAR
        st.markdown(
            f"<h1 style='text-align:center; font-size:60px; "
            f"color:#16a34a; margin-bottom:0'>₹{format_inr(value, 4)}</h1>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<p style='text-align:center; color:#6b7280;'>"
            f"Growth so far: ₹{format_inr(gain)} &nbsp;·&nbsp; "
            f"+₹{per_sec:.4f}/sec</p>",
            unsafe_allow_html=True,
        )

    counter()

    # add / subtract
    st.subheader("Adjust the balance")
    col_in, col_add, col_sub = st.columns([2, 1, 1])
    with col_in:
        amount_x = st.number_input(
            "Amount (₹)", min_value=0.0, value=0.0, step=10000.0,
            label_visibility="collapsed", placeholder="Enter amount",
        )
    with col_add:
        add_clicked = st.button("➕ Add", use_container_width=True)
    with col_sub:
        sub_clicked = st.button("➖ Subtract", use_container_width=True)

    if add_clicked and amount_x > 0:
        st.session_state.adjustments.append({"ts": datetime.now(IST), "amount": amount_x})
        save_adjustments(st.session_state.adjustments)
        st.rerun()
    if sub_clicked and amount_x > 0:
        st.session_state.adjustments.append({"ts": datetime.now(IST), "amount": -amount_x})
        save_adjustments(st.session_state.adjustments)
        st.rerun()

    st.caption("Open **Charts** in the sidebar to see growth and daily-generation graphs.")


# ==================== CHARTS PAGE ====================
def charts_page():
    sidebar_details()
    st.title("📊 Charts")

    start_naive = START_DT.replace(tzinfo=None)
    now_naive = datetime.now(IST).replace(tzinfo=None)

    # ---- growth over time (real growth only) ----
    st.subheader("📈 Real growth over time")

    UNIT = {
        "Days":   ("D",  365, 30, lambda n: pd.DateOffset(days=n)),
        "Weeks":  ("W",  104, 12, lambda n: pd.DateOffset(weeks=n)),
        "Months": ("MS", 120, 12, lambda n: pd.DateOffset(months=n)),
        "Years":  ("YS",  50,  5, lambda n: pd.DateOffset(years=n)),
    }
    c1, c2 = st.columns([1, 1])
    with c1:
        unit = st.selectbox("View by", list(UNIT.keys()), index=0)
    freq, max_count, default_count, offset_of = UNIT[unit]
    with c2:
        count = st.slider(f"Look back ({unit.lower()})", 1, max_count, default_count)

    window_start = max(start_naive, now_naive - offset_of(count))
    idx = pd.date_range(start=window_start, end=now_naive, freq=freq)
    adj_pts = [
        a["ts"].astimezone(IST).replace(tzinfo=None)
        for a in st.session_state.adjustments
        if window_start <= a["ts"].astimezone(IST).replace(tzinfo=None) <= now_naive
    ]
    idx = idx.union(pd.DatetimeIndex([window_start, now_naive] + adj_pts)).sort_values()

    line_df = pd.DataFrame({
        "Date": idx,
        "Value": [value_at(p.to_pydatetime().replace(tzinfo=IST)) for p in idx],
    })
    line = (
        alt.Chart(line_df)
        .mark_line(color="#16a34a", point=alt.OverlayMarkDef(color="#16a34a", size=30))
        .encode(
            x=alt.X("Date:T", title="Time"),
            y=alt.Y("Value:Q", title="Value (₹)", axis=alt.Axis(format=",.0f"),
                    scale=alt.Scale(zero=False)),
            tooltip=[alt.Tooltip("Date:T", title="Date", format="%d %b %Y, %H:%M"),
                     alt.Tooltip("Value:Q", title="Value (₹)", format=",.2f")],
        )
        .properties(height=340)
        .interactive()
    )
    st.altair_chart(line, use_container_width=True)
    st.caption(
        f"Real growth, {window_start.strftime('%d %b %Y')} → "
        f"{now_naive.strftime('%d %b %Y')} · sampled {unit.lower()}. "
        "Add/subtract events appear as steps in the line."
    )

    st.divider()

    # ---- money generated per day (bar chart / histogram) ----
    st.subheader("📊 Money generated per day")
    st.caption("Pure investment returns earned each day (deposits/withdrawals excluded).")

    rows = []
    day = start_naive
    while day.date() <= now_naive.date():
        day_start = max(start_naive, day)
        day_end = min(now_naive, day + timedelta(days=1))
        if day_end <= day_start:
            break
        delta = (value_at(day_end.replace(tzinfo=IST))
                 - value_at(day_start.replace(tzinfo=IST)))
        # remove the raw deposits/withdrawals made during the day to isolate returns
        adj_in_day = sum(
            a["amount"] for a in st.session_state.adjustments
            if day_start <= a["ts"].astimezone(IST).replace(tzinfo=None) < day_end
        )
        rows.append({"Day": day.date(), "Generated": delta - adj_in_day})
        day += timedelta(days=1)

    bar_df = pd.DataFrame(rows)
    bars = (
        alt.Chart(bar_df)
        .mark_bar(color="#16a34a")
        .encode(
            x=alt.X("Day:T", title="Day"),
            y=alt.Y("Generated:Q", title="Generated that day (₹)",
                    axis=alt.Axis(format=",.0f")),
            tooltip=[alt.Tooltip("Day:T", title="Day", format="%d %b %Y"),
                     alt.Tooltip("Generated:Q", title="Generated (₹)", format=",.2f")],
        )
        .properties(height=320)
    )
    st.altair_chart(bars, use_container_width=True)
    if not bar_df.empty:
        st.caption(
            f"{len(bar_df)} day(s) · total generated so far: "
            f"₹{format_inr(bar_df['Generated'].sum())}. "
            "Daily amounts rise gradually as the compounding base grows."
        )

    st.divider()

    # ---- adjustment history ----
    if st.session_state.adjustments:
        with st.expander(f"Adjustment history ({len(st.session_state.adjustments)})"):
            for adj in reversed(st.session_state.adjustments):
                sign = "＋" if adj["amount"] >= 0 else "－"
                st.write(
                    f"{sign} ₹{format_inr(abs(adj['amount']))}  ·  "
                    f"{adj['ts'].astimezone(IST).strftime('%d %b %Y, %H:%M:%S')} IST"
                )
        if st.button("Reset adjustments"):
            st.session_state.adjustments = []
            save_adjustments([])
            st.rerun()


# ==================== navigation ====================
nav = st.navigation([
    st.Page(home_page, title="Home", icon="💰", default=True),
    st.Page(charts_page, title="Charts", icon="📊"),
])
nav.run()
