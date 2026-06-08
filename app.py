"""
Real-time wealth counter.

Starts at INR 70,00,000 (70 lakh) and grows at an assumed 10% per annum,
compounded smoothly every second. Growth is anchored to a start date
(default: today).

You can also add or subtract a lump sum at any time. Each adjustment is
applied at the moment you click, and from that point onward it compounds
at 10% along with the rest of the balance.
"""

import time
from datetime import date, datetime

import streamlit as st

PRINCIPAL = 7_000_000        # INR 70,00,000
ANNUAL_RATE = 0.10           # 10% per annum
SECONDS_PER_YEAR = 365.25 * 24 * 60 * 60


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


def current_value(now: datetime) -> float:
    """Grown principal plus every grown adjustment."""
    total = grow(PRINCIPAL, st.session_state.start_dt, now)
    for adj in st.session_state.adjustments:
        total += grow(adj["amount"], adj["ts"], now)
    return total


def total_contributed() -> float:
    """Principal plus the raw (un-grown) value of all adjustments."""
    return PRINCIPAL + sum(adj["amount"] for adj in st.session_state.adjustments)


st.set_page_config(page_title="Wealth Counter", page_icon="💰", layout="centered")

# ---- state ----
if "adjustments" not in st.session_state:
    st.session_state.adjustments = []   # list of {"ts": datetime, "amount": float}
if "start_dt" not in st.session_state:
    st.session_state.start_dt = datetime.combine(date.today(), datetime.min.time())

st.title("💰 Live Wealth Counter")
st.caption("Starting at ₹70,00,000 · assumed 10% per annum")

# ---- sidebar ----
with st.sidebar:
    st.header("Settings")
    start_date = st.date_input("Growth start date", value=st.session_state.start_dt.date())
    st.session_state.start_dt = datetime.combine(start_date, datetime.min.time())
    st.write(f"Principal: ₹{format_inr(PRINCIPAL)}")
    st.write(f"Rate: {ANNUAL_RATE * 100:.0f}% per annum")

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
    st.session_state.adjustments.append({"ts": datetime.now(), "amount": amount_x})
    st.rerun()
if sub_clicked and amount_x > 0:
    st.session_state.adjustments.append({"ts": datetime.now(), "amount": -amount_x})
    st.rerun()

# ---- live counter (reruns on its own without blocking the buttons) ----
@st.fragment(run_every=0.05)
def counter():
    now = datetime.now()
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

# ---- adjustment history ----
if st.session_state.adjustments:
    with st.expander(f"Adjustment history ({len(st.session_state.adjustments)})"):
        for i, adj in enumerate(reversed(st.session_state.adjustments)):
            sign = "＋" if adj["amount"] >= 0 else "－"
            st.write(
                f"{sign} ₹{format_inr(abs(adj['amount']))}  ·  "
                f"{adj['ts'].strftime('%d %b %Y, %H:%M:%S')}"
            )
    if st.button("Reset adjustments"):
        st.session_state.adjustments = []
        st.rerun()
