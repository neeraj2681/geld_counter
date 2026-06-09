"""
Real-time wealth counter.

Starts at INR 70,00,000 (70 lakh) on a FIXED anchor date of 8 June 2026 (IST)
and grows at an assumed 10% per annum, compounded smoothly every second.
Because the start date is constant, the balance keeps continuing across days
and sessions — it never resets.

You can also add or subtract a lump sum at any time. Each adjustment is applied
at the moment you click and, from that point onward, compounds at 10% along with
the rest of the balance. Adjustments are saved to disk so they persist too.
"""

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st

PRINCIPAL = 7_000_000        # INR 70,00,000
ANNUAL_RATE = 0.10           # 10% per annum
SECONDS_PER_YEAR = 365.25 * 24 * 60 * 60

IST = ZoneInfo("Asia/Kolkata")
START_DT = datetime(2026, 6, 8, 0, 0, 0, tzinfo=IST)   # FIXED anchor — never resets

ADJ_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adjustments.json")


def load_adjustments() -> list:
    """Load saved adjustments from disk."""
    if not os.path.exists(ADJ_FILE):
        return []
    try:
        with open(ADJ_FILE) as f:
            raw = json.load(f)
        return [{"ts": datetime.fromisoformat(a["ts"]), "amount": float(a["amount"])} for a in raw]
    except Exception:
        return []


def save_adjustments(adjustments: list) -> None:
    """Persist adjustments to disk."""
    data = [{"ts": a["ts"].isoformat(), "amount": a["amount"]} for a in adjustments]
    with open(ADJ_FILE, "w") as f:
        json.dump(data, f, indent=2)


def format_inr(amount: float, decimals: int = 2) -> str:
    """Format a number with the Indian grouping system (e.g. 7,00,00,000.00)."""
    neg = amount < 0
    amount = abs(amount)
    whole = int(amount)
    frac = f"{amount - whole:.{decimals}f}"[2:]  # fractional digits

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
    """Compound `amount` at the annual rate from `since` to `now`."""
    years = (now - since).total_seconds() / SECONDS_PER_YEAR
    return amount * (1 + ANNUAL_RATE) ** years


def value_at(t: datetime) -> float:
    """Value at time `t`: grown principal plus adjustments that already happened by `t`."""
    total = grow(PRINCIPAL, START_DT, t)
    for adj in st.session_state.adjustments:
        if adj["ts"] <= t:
            total += grow(adj["amount"], adj["ts"], t)
    return total


def current_value(now: datetime) -> float:
    """Convenience wrapper for the value right now."""
    return value_at(now)


def total_contributed() -> float:
    """Principal plus the raw (un-grown) value of all adjustments."""
    return PRINCIPAL + sum(adj["amount"] for adj in st.session_state.adjustments)


st.set_page_config(page_title="Wealth Counter", page_icon="💰", layout="centered")

# ---- state ----
if "adjustments" not in st.session_state:
    st.session_state.adjustments = load_adjustments()

st.title("💰 Live Wealth Counter")
st.caption("Starting at ₹70,00,000 · assumed 10% per annum")

# ---- sidebar ----
with st.sidebar:
    st.header("Details")
    st.write(f"**Anchor date:** {START_DT.strftime('%d %b %Y')} (IST)")
    st.write(f"**Principal:** ₹{format_inr(PRINCIPAL)}")
    st.write(f"**Rate:** {ANNUAL_RATE * 100:.0f}% per annum")
    st.caption("Start date is fixed — the balance continues across days and never resets.")

# ---- add / subtract controls ----
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

# ---- live counter (reruns on its own without blocking the buttons) ----
@st.fragment(run_every=0.05)
def counter():
    now = datetime.now(IST)
    value = current_value(now)
    gain = value - total_contributed()
    # instantaneous growth rate (₹ per second) so you can see it's live
    per_sec = value * ANNUAL_RATE / SECONDS_PER_YEAR
    # show 4 decimals so the real-time ticking is visible
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

# ---- growth chart (real growth only: anchor -> now) ----
st.subheader("📈 Real growth over time")

start_naive = START_DT.replace(tzinfo=None)
now_naive = datetime.now(IST).replace(tzinfo=None)

# unit -> (pandas sampling freq, slider max, slider default, DateOffset builder)
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

# window = last `count` units, but never earlier than the fixed anchor
window_start = max(start_naive, now_naive - offset_of(count))

# sampled points + the exact window edges + every adjustment moment (so steps show)
idx = pd.date_range(start=window_start, end=now_naive, freq=freq)
adj_pts = [
    a["ts"].astimezone(IST).replace(tzinfo=None)
    for a in st.session_state.adjustments
    if window_start <= a["ts"].astimezone(IST).replace(tzinfo=None) <= now_naive
]
idx = idx.union(pd.DatetimeIndex([window_start, now_naive] + adj_pts)).sort_values()

df = pd.DataFrame({
    "Date": idx,
    "Value": [value_at(p.to_pydatetime().replace(tzinfo=IST)) for p in idx],
})

chart = (
    alt.Chart(df)
    .mark_line(color="#16a34a", point=alt.OverlayMarkDef(color="#16a34a", size=30))
    .encode(
        x=alt.X("Date:T", title="Time"),
        y=alt.Y("Value:Q", title="Value (₹)", axis=alt.Axis(format=",.0f"),
                scale=alt.Scale(zero=False)),
        tooltip=[alt.Tooltip("Date:T", title="Date", format="%d %b %Y, %H:%M"),
                 alt.Tooltip("Value:Q", title="Value (₹)", format=",.2f")],
    )
    .properties(height=360)
    .interactive()
)
st.altair_chart(chart, use_container_width=True)
st.caption(
    f"Real growth, {window_start.strftime('%d %b %Y')} → "
    f"{now_naive.strftime('%d %b %Y')} · sampled {unit.lower()}. "
    "Add/subtract events appear as steps in the line."
)

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
