"""
app.py — Atlas Dental patient-facing chat UI.

Color scheme from atlasdental.ca:
  Gold accent:   #CC9933
  Dark text:     #222222
  Secondary:     #7A8896
  Page bg:       #EFEAE0

Run: streamlit run app.py  →  http://localhost:8501
"""
import html
import os
import re
import uuid
from datetime import datetime

import streamlit as st

from src.agents.runner import stream_agent

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Atlas Dental — AI Receptionist",
    page_icon="🦷",
    layout="centered",
    initial_sidebar_state="expanded",
)

# ── Access gate ───────────────────────────────────────────────────────────────
# Public demo link with no rate limiting; a shared passphrase keeps random
# internet traffic from triggering real Claude/Gmail/Calendar calls.

_ACCESS_CODE = os.getenv("APP_ACCESS_PASSPHRASE", "")
if _ACCESS_CODE:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.markdown(
            "<div style='text-align:center; margin-top:15vh;'>"
            "<div style='font-size:2.5rem;'>🦷</div>"
            "<div style='font-size:1.2rem; font-weight:700; margin-bottom:6px;'>Atlas Dental</div>"
            "<div style='color:#7A8896; font-size:0.9rem; margin-bottom:18px;'>"
            "This demo is private. Enter the access code to continue.</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        col = st.columns([1, 2, 1])[1]
        with col:
            entered = st.text_input("Access code", type="password", label_visibility="collapsed", placeholder="Access code")
            if st.button("Enter", use_container_width=True):
                if entered == _ACCESS_CODE:
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("Incorrect code.")
        st.stop()

# ── Icons (inline SVG, stroke matches surrounding text color via currentColor) ─

_ICON_TOOTH = """<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.4"><path d="M12 2.5c-2 0-3.4 1.4-3.4 3.1 0 .9-.3 1.8-.9 2.7-1 1.4-1.5 3-1.5 4.9 0 3.1 1 6.8 2.4 6.8.9 0 1.2-1.8 1.5-3.3.2-1 .6-1.5 1.9-1.5s1.7.5 1.9 1.5c.3 1.5.6 3.3 1.5 3.3 1.4 0 2.4-3.7 2.4-6.8 0-1.9-.5-3.5-1.5-4.9-.6-.9-.9-1.8-.9-2.7 0-1.7-1.4-3.1-3.4-3.1z"/></svg>"""

_ICON_LOCATION = """<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.8"><path d="M12 21s7-7.5 7-12a7 7 0 10-14 0c0 4.5 7 12 7 12z"/><circle cx="12" cy="9" r="2.4"/></svg>"""

_ICON_PHONE = """<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.8"><path d="M6.6 10.8c1.4 2.8 3.7 5.1 6.5 6.6l2.1-2.1c.3-.3.7-.4 1.1-.2 1.1.5 2.3.8 3.5.8.6 0 1 .4 1 1v3.3c0 .6-.4 1-1 1C11.7 21.2 2.9 12.4 2.9 4c0-.6.4-1 1-1H7.2c.6 0 1 .4 1 1 0 1.2.3 2.4.8 3.5.2.4.1.8-.2 1.1l-2.2 2.2z"/></svg>"""

_ICON_CLOCK = """<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.8"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></svg>"""

_ICON_INFO = """<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.8"><path d="M21 11.5a8.4 8.4 0 01-8.4 8.4c-1.2 0-2.4-.3-3.4-.8L4 20l1-4.9a8.3 8.3 0 01-.9-3.6A8.4 8.4 0 0112.6 3.1 8.4 8.4 0 0121 11.5z"/></svg>"""

_ICON_CALENDAR = """<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.8"><rect x="3.5" y="4.5" width="17" height="16" rx="2.5"/><path d="M3.5 9.5h17M8 3v3M16 3v3"/></svg>"""

_ICON_CHECK = """<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>"""

_ICON_BOT = """<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.8"><rect x="4" y="4" width="16" height="14" rx="3"/><path d="M9 10v0M15 10v0M8 15h8"/></svg>"""


def _icon(svg_template: str, size: int = 17, color: str = "#CC9933") -> str:
    return svg_template.format(size=size, color=color)


# ── CSS ───────────────────────────────────────────────────────────────────────

st.markdown(
    """<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Lora:wght@500;600;700&family=Public+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">""",
    unsafe_allow_html=True,
)

st.markdown("""
<style>
@keyframes ad-pulse { 0%,100%{opacity:1} 50%{opacity:.35} }

html, body, .stApp, .stApp *:not([data-testid="stIconMaterial"]) {
    font-family: 'Public Sans', sans-serif;
}
.stApp, .stApp > div {
    background-color: #EFEAE0 !important;
}
.block-container {
    padding-top: 4.5rem !important;
    padding-bottom: 1rem !important;
    max-width: 820px !important;
}

/* Mobile: tighter side padding, wider bubbles so they don't cramp */
@media (max-width: 480px) {
    .block-container {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }
    .ad-bubble-user, .ad-bubble-row-assistant {
        max-width: 92% !important;
    }
}

/* Fix dark sticky-bottom container */
.stBottom, [data-testid="stBottom"],
[data-testid="stBottomBlockContainer"],
section[data-testid="stBottomBlockContainer"] {
    background-color: #FAFAF8 !important;
    background: #FAFAF8 !important;
    border-top: 1px solid #E0D9CC !important;
}

/* Chat input */
[data-testid="stChatInput"] textarea, .stChatInput textarea {
    background: #FFFFFF !important;
    border: 1.5px solid #DADADA !important;
    border-radius: 26px !important;
    padding: 12px 18px !important;
    color: #222222 !important;
    font-size: 0.95rem !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06) !important;
    outline: none !important;
}
[data-testid="stChatInput"] textarea:focus, .stChatInput textarea:focus {
    border-color: #CC9933 !important;
    box-shadow: 0 0 0 3px rgba(204,153,51,0.14) !important;
}
[data-testid="stChatInput"] textarea:invalid,
[data-testid="stChatInput"] textarea[aria-invalid] {
    border-color: #DADADA !important;
    box-shadow: none !important;
}

/* Send button */
[data-testid="stChatInput"] button, .stChatInput button {
    background-color: #CC9933 !important;
    border: none !important;
    border-radius: 50% !important;
    color: #fff !important;
}
[data-testid="stChatInput"] button:hover, .stChatInput button:hover {
    background-color: #B8882D !important;
}

/* Chat avatars */
[data-testid="chatAvatarIcon-user"] {
    background-color: #CC9933 !important;
    color: #fff !important;
}
[data-testid="chatAvatarIcon-assistant"] {
    background-color: #2F2F2F !important;
    color: #fff !important;
}

/* Quick-reply + sidebar buttons */
.stButton > button {
    background: #FFFFFF !important;
    color: #9A7420 !important;
    border: 1.5px solid #CC9933 !important;
    border-radius: 22px !important;
    font-size: 0.84rem !important;
    font-weight: 500 !important;
    padding: 6px 18px !important;
    transition: all 0.16s ease !important;
    box-shadow: 0 1px 3px rgba(204,153,51,0.12) !important;
    margin-top: 4px !important;
}
.stButton > button:hover {
    background: #CC9933 !important;
    color: #FFFFFF !important;
    box-shadow: 0 2px 8px rgba(204,153,51,0.28) !important;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background-color: #FFFFFF !important;
    border-right: 1px solid #E8E4DC !important;
}
hr {
    border: none !important;
    border-top: 1px solid #DADADA !important;
    margin: 10px 0 !important;
}

/* Info cards */
.ad-card {
    background:#FBFAF7; border:1px solid #EFEAE0; border-radius:12px;
    padding:14px 16px; display:flex; gap:10px; margin-bottom:12px;
}
.ad-card-icon { flex:none; margin-top:1px; }
.ad-card-title { font:700 12.5px 'Public Sans'; color:#222; margin-bottom:3px; }
.ad-card-body { font:400 13px 'Public Sans'; color:#5D6670; line-height:1.5; }
.ad-card-body a { color:#9A7420; text-decoration:underline; }

/* Chat bubbles */
.ad-bubble-row-user {
    display:flex; flex-direction:column; align-items:flex-end; gap:4px; margin:0 0 16px 0;
}
.ad-bubble-user {
    background:#CC9933; color:#fff; border-radius:16px 16px 4px 16px;
    padding:11px 16px; font:500 14px 'Public Sans'; max-width:75%;
}
.ad-bubble-meta-user { font:400 11px 'Public Sans'; color:#9CA3AC; }

.ad-bubble-row-assistant { display:flex; gap:10px; max-width:85%; margin:0 0 16px 0; }
.ad-avatar-assistant {
    width:30px; height:30px; border-radius:9px; background:#2F2F2F; flex:none;
    display:flex; align-items:center; justify-content:center;
}
.ad-bubble-assistant-col { display:flex; flex-direction:column; gap:6px; width:100%; }
.ad-bubble-assistant-head { display:flex; align-items:center; gap:6px; }
.ad-bubble-assistant-name { font:700 12px 'Public Sans'; color:#222; }
.ad-bubble-assistant-time { font:400 11px 'Public Sans'; color:#9CA3AC; }
.ad-bubble-assistant {
    background:#F2F0EB; border-radius:4px 16px 16px 16px; padding:12px 16px;
    font:400 14px 'Public Sans'; color:#222; line-height:1.55;
}
.ad-bubble-assistant p { margin:0 0 0.6em 0; }
.ad-bubble-assistant p:last-child { margin-bottom:0; }
.ad-msg-table {
    border-collapse:collapse; width:100%; margin:0 0 0.6em 0; font-size:13px;
}
.ad-msg-table th, .ad-msg-table td {
    text-align:left; padding:5px 10px; border-bottom:1px solid #E0DACE;
}
.ad-msg-table th { color:#8B93A0; font-weight:600; font-size:11px; text-transform:uppercase; }

/* Live status rail */
.ad-status-rail {
    display:flex; align-items:center; gap:8px; background:#FBF3E3;
    border:1px solid #F1E3C4; border-radius:10px; padding:9px 14px;
    font:600 12px 'Public Sans'; color:#9A7420; margin-bottom:8px;
}
.ad-status-dot {
    width:6px; height:6px; border-radius:50%; background:#CC9933;
    animation: ad-pulse 1.4s infinite; flex:none;
}

/* Structured summary card */
.ad-summary-card {
    background:#fff; border:1px solid #E8E4DC; border-radius:14px; overflow:hidden;
    box-shadow:0 2px 10px rgba(0,0,0,0.04); margin-top:8px; margin-bottom:10px;
}
.ad-summary-head {
    background:#FBF3E3; padding:12px 18px; display:flex; align-items:center; gap:8px;
    font:700 13px 'Public Sans'; color:#9A7420;
}
.ad-summary-body { padding:16px 18px; display:flex; flex-direction:column; gap:11px; }
.ad-summary-row { display:flex; gap:10px; }
.ad-summary-row-icon { flex:none; margin-top:2px; }
.ad-summary-row-label { font:600 11px 'Public Sans'; color:#8B93A0; }
.ad-summary-row-value { font:500 13.5px 'Public Sans'; color:#222; }
.ad-summary-footer {
    border-top:1px solid #EFEAE0; padding:10px 18px;
    font:400 12.5px 'Public Sans'; color:#8B93A0;
}
</style>
""", unsafe_allow_html=True)


def _now_str() -> str:
    return datetime.now().strftime("%I:%M %p").lstrip("0")


_TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$")


def _table_row_cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _md_to_html(text: str) -> str:
    """Escape raw text for safe HTML embedding, then convert the small subset of
    markdown the agent actually produces (**bold**, '- ' bullet lists, GFM tables,
    paragraphs). Streamlit's markdown parser doesn't run on text nested inside raw
    HTML tags, so this has to happen manually rather than relying on st.markdown.
    Tables are a defense-in-depth fallback — booking_prompt.md instructs the agent
    not to restate booking details as a table since the summary card already does.
    """
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)

    blocks = []
    for block in escaped.split("\n\n"):
        lines = [line for line in block.split("\n")]
        non_empty = [line for line in lines if line.strip()]

        if (
            len(non_empty) >= 2
            and non_empty[0].strip().startswith("|")
            and _TABLE_SEP_RE.match(non_empty[1].strip())
        ):
            header = _table_row_cells(non_empty[0])
            head_html = "".join(f"<th>{c}</th>" for c in header)
            body_html = "".join(
                "<tr>" + "".join(f"<td>{c}</td>" for c in _table_row_cells(row)) + "</tr>"
                for row in non_empty[2:]
            )
            blocks.append(
                f'<table class="ad-msg-table"><thead><tr>{head_html}</tr></thead>'
                f"<tbody>{body_html}</tbody></table>"
            )
        elif non_empty and all(line.strip().startswith("- ") for line in non_empty):
            items = "".join(f"<li>{line.strip()[2:]}</li>" for line in non_empty)
            blocks.append(f'<ul style="margin:0 0 0.6em 1.1em; padding:0;">{items}</ul>')
        elif block.strip():
            blocks.append(f"<p>{'<br>'.join(lines)}</p>")
    return "".join(blocks)


def _user_bubble_html(text: str, ts: str) -> str:
    return (
        f'<div class="ad-bubble-row-user"><div class="ad-bubble-user">{_md_to_html(text)}</div>'
        f'<div class="ad-bubble-meta-user">You · {html.escape(ts)}</div></div>'
    )


def _assistant_bubble_html(text: str, ts: str) -> str:
    return f"""<div class="ad-bubble-row-assistant">
    <div class="ad-avatar-assistant">{_icon(_ICON_BOT, 15, '#fff')}</div>
    <div class="ad-bubble-assistant-col">
        <div class="ad-bubble-assistant-head">
            <span class="ad-bubble-assistant-name">Atlas Assistant</span>
            <span class="ad-bubble-assistant-time">{html.escape(ts)}</span>
        </div>
        <div class="ad-bubble-assistant">{_md_to_html(text)}</div>
    </div>
</div>"""


def _render_summary_card(summary: dict) -> None:
    name = html.escape(summary.get("name") or "there")
    service = html.escape(summary.get("service", ""))
    when = html.escape(summary.get("datetime", ""))
    location = html.escape(summary.get("location", ""))
    footer = html.escape(summary.get("footer", ""))
    st.markdown(
        f"""<div class="ad-summary-card">
    <div class="ad-summary-head">{_icon(_ICON_CHECK, 16, '#9A7420')}<span>You're all set, {name}</span></div>
    <div class="ad-summary-body">
        <div class="ad-summary-row">{_icon(_ICON_TOOTH, 15)}<div><div class="ad-summary-row-label">APPOINTMENT</div><div class="ad-summary-row-value">{service}</div></div></div>
        <div class="ad-summary-row">{_icon(_ICON_CALENDAR, 15)}<div><div class="ad-summary-row-label">DATE &amp; TIME</div><div class="ad-summary-row-value">{when}</div></div></div>
        <div class="ad-summary-row">{_icon(_ICON_LOCATION, 15)}<div><div class="ad-summary-row-label">LOCATION</div><div class="ad-summary-row-value">{location}</div></div></div>
    </div>
    <div class="ad-summary-footer">{footer}</div>
</div>""",
        unsafe_allow_html=True,
    )


# ── Session state ─────────────────────────────────────────────────────────────

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_input" not in st.session_state:
    st.session_state.pending_input = None

# ── Consume pending quick-reply FIRST, before any widget is rendered ──────────
# This must happen at the top so it's available before the chat_input call.
# Button clicks auto-trigger a rerun; the value is in session_state on that rerun.

user_input: str | None = None
if st.session_state.pending_input:
    user_input = st.session_state.pending_input
    st.session_state.pending_input = None

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown(
        f"""<div style="text-align:center; padding:12px 0 20px 0;">
        <div>{_icon(_ICON_TOOTH, 34)}</div>
        <div style="font:700 19px 'Lora',serif; color:#222222; margin-top:6px;">
            Atlas Dental
        </div>
        <div style="font-size:0.75rem; color:#9A7420; font-weight:700;
                    letter-spacing:0.6px; text-transform:uppercase; margin-top:4px;
                    background:#FBF3E3; display:inline-block; padding:3px 10px; border-radius:999px;">
            Downtown Toronto
        </div>
    </div>""",
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""<div class="ad-card"><span class="ad-card-icon">{_icon(_ICON_LOCATION, 17)}</span>
        <div><div class="ad-card-title">Location</div>
        <div class="ad-card-body">2 Bloor St W, Suite 1903<br>Toronto, ON M4W 3E2</div></div></div>""",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""<div class="ad-card"><span class="ad-card-icon">{_icon(_ICON_PHONE, 17)}</span>
        <div><div class="ad-card-title">Contact</div>
        <div class="ad-card-body">416-597-0534<br><a href="mailto:info@atlasdental.ca">info@atlasdental.ca</a></div></div></div>""",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""<div class="ad-card"><span class="ad-card-icon">{_icon(_ICON_CLOCK, 17)}</span>
        <div><div class="ad-card-title">Hours</div>
        <div class="ad-card-body">Mon – Fri: 8 am – 6 pm<br>Saturday: By appointment<br>Sunday: Closed</div></div></div>""",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""<div class="ad-card"><span class="ad-card-icon">{_icon(_ICON_INFO, 17)}</span>
        <div><div class="ad-card-title">About this assistant</div>
        <div class="ad-card-body">I can help you book appointments, answer pricing questions, and connect you with the clinic team.</div></div></div>""",
        unsafe_allow_html=True,
    )

    if st.button("↩ Start New Conversation", use_container_width=True):
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.pending_input = None
        # no st.rerun() needed — button click already triggers one

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown(
    f"""<div style="display:flex; align-items:center; gap:12px;
            padding:14px 0 12px 0; border-bottom:2px solid #CC9933; margin-bottom:10px;">
    <div style="width:44px; height:44px; border-radius:10px; background:#FBF3E3;
                display:flex; align-items:center; justify-content:center; flex:none;">
        {_icon(_ICON_TOOTH, 21)}
    </div>
    <div>
        <div style="font:700 1.35rem 'Lora',serif; color:#222222; line-height:1.2;">
            Atlas Dental
        </div>
        <div style="font-size:0.78rem; color:#9A7420; letter-spacing:0.4px; margin-top:2px;
                    display:flex; align-items:center; gap:5px;">
            <span style="width:7px; height:7px; border-radius:50%; background:#4C9A62;"></span>
            AI RECEPTIONIST &nbsp;·&nbsp; HERE TO HELP
        </div>
    </div>
</div>""",
    unsafe_allow_html=True,
)

# ── Welcome card + starter prompts (only before first message) ────────────────

if not st.session_state.messages and not user_input:
    st.markdown("""
    <div style="background:#FFFFFF; border:1px solid #E8E4DC; border-left:4px solid #CC9933;
                border-radius:12px; padding:22px 26px; margin:18px 0 16px 0;
                box-shadow:0 2px 10px rgba(0,0,0,0.05);">
        <div style="font-size:1.05rem; font-weight:600; color:#222222; margin-bottom:8px;">
            👋 Welcome to Atlas Dental
        </div>
        <div style="font-size:0.88rem; color:#7A8896; line-height:1.65;">
            I'm your AI receptionist. I can help you book an appointment, answer questions
            about our services and pricing, or connect you with our team.
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(
        "<div style='font-size:0.82rem; color:#7A8896; margin-bottom:8px;'>"
        "How can I help you today?</div>",
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("📅 Book\nan appointment"):
        st.session_state.pending_input = "I'd like to book an appointment"
        st.rerun()
    if c2.button("💰 Pricing\n& estimates"):
        st.session_state.pending_input = "What are your prices for common procedures?"
        st.rerun()
    if c3.button("🏥 Clinic hours\n& location"):
        st.session_state.pending_input = "What are your clinic hours and where are you located?"
        st.rerun()
    if c4.button("🚨 Dental\nemergency"):
        st.session_state.pending_input = "I'm having a dental emergency and need urgent help"
        st.rerun()

# ── Conversation history ──────────────────────────────────────────────────────

for i, msg in enumerate(st.session_state.messages):
    if msg["role"] == "user":
        st.markdown(_user_bubble_html(msg["text"], msg.get("ts", "")), unsafe_allow_html=True)
    else:
        st.markdown(_assistant_bubble_html(msg["text"], msg.get("ts", "")), unsafe_allow_html=True)
        if msg.get("summary"):
            _render_summary_card(msg["summary"])

    # Quick replies only after the LAST assistant message, and only when idle
    is_last_msg = i == len(st.session_state.messages) - 1
    if msg["role"] == "assistant" and is_last_msg and not user_input:
        qr = (msg.get("quick_replies") or [])[:4]
        if qr:
            cols = st.columns(len(qr))
            for col, option in zip(cols, qr):
                if col.button(option, key=f"qr_{i}_{option}"):
                    st.session_state.pending_input = option
                    st.rerun()

# ── Chat input — ALWAYS called every run ─────────────────────────────────────
# Streamlit requires every widget to be called on every run.
# If user typed something AND there's a pending quick reply (can't happen in
# practice), the quick reply from the top of this run wins.

typed = st.chat_input("How can we help you today?")
if not user_input and typed:
    user_input = typed

# ── Process user turn ─────────────────────────────────────────────────────────

if user_input:
    user_ts = _now_str()
    st.session_state.messages.append({"role": "user", "text": user_input, "ts": user_ts})
    st.markdown(_user_bubble_html(user_input, user_ts), unsafe_allow_html=True)

    meta: dict = {}
    status_placeholder = st.empty()
    accumulated = ""

    for kind, chunk in stream_agent(user_input, st.session_state.thread_id, meta):
        if kind == "status":
            status_placeholder.markdown(
                f'<div class="ad-status-rail"><span class="ad-status-dot"></span>{chunk}</div>',
                unsafe_allow_html=True,
            )
        else:
            accumulated += chunk

    status_placeholder.empty()
    full_text = accumulated
    assistant_ts = _now_str()
    st.markdown(_assistant_bubble_html(full_text, assistant_ts), unsafe_allow_html=True)
    if meta.get("summary"):
        _render_summary_card(meta["summary"])

    st.session_state.messages.append({
        "role": "assistant",
        "text": full_text or "",
        "quick_replies": meta.get("quick_replies") or [],
        "ts": assistant_ts,
        "summary": meta.get("summary"),
    })
