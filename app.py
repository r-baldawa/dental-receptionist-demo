"""
app.py — Atlas Dental patient-facing chat UI.

Color scheme from atlasdental.ca:
  Gold accent:   #CC9933
  Dark text:     #222222
  Secondary:     #7A8896
  Light bg:      #FAFAF8

Run: streamlit run app.py  →  http://localhost:8501
"""
import os
import uuid
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

# ── CSS ───────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
.stApp, .stApp > div {
    background-color: #FAFAF8 !important;
}
.block-container {
    padding-top: 4.5rem !important;
    padding-bottom: 1rem !important;
    max-width: 760px !important;
}

/* Mobile: tighter side padding, smaller header text so it doesn't wrap awkwardly */
@media (max-width: 480px) {
    .block-container {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
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
</style>
""", unsafe_allow_html=True)

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
    st.markdown("""
    <div style="text-align:center; padding:12px 0 20px 0;">
        <div style="font-size:2.8rem; line-height:1;">🦷</div>
        <div style="font-size:1.15rem; font-weight:700; color:#222222; margin-top:6px;">
            Atlas Dental
        </div>
        <div style="font-size:0.75rem; color:#CC9933; font-weight:600;
                    letter-spacing:0.8px; text-transform:uppercase; margin-top:2px;">
            Downtown Toronto
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("**📍 Location**")
    st.markdown("1002 Bloor Street West  \nToronto, ON M6H 1M4")
    st.markdown("**📞 Contact**")
    st.markdown("416-597-0534  \ninfo@atlasdental.ca")
    st.markdown("**🕐 Hours**")
    st.markdown("Mon – Fri: 8 am – 6 pm  \nSaturday: By appointment  \nSunday: Closed")
    st.markdown("---")
    st.markdown("**About this assistant**")
    st.caption(
        "I can help you book appointments, answer pricing questions, "
        "and connect you with the clinic team."
    )
    st.markdown("---")

    if st.button("↩ Start New Conversation", use_container_width=True):
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.pending_input = None
        # no st.rerun() needed — button click already triggers one

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""
<div style="display:flex; align-items:center; gap:12px;
            padding:14px 0 12px 0; border-bottom:2px solid #CC9933; margin-bottom:10px;">
    <div style="font-size:2rem; line-height:1;">🦷</div>
    <div>
        <div style="font-size:1.35rem; font-weight:700; color:#222222; line-height:1.2;">
            Atlas Dental
        </div>
        <div style="font-size:0.78rem; color:#9A7420; letter-spacing:0.4px; margin-top:2px;">
            <span style="display:inline-block; width:7px; height:7px; border-radius:50%;
                         background:#CC9933; margin-right:5px; vertical-align:middle;"></span>
            AI RECEPTIONIST &nbsp;·&nbsp; HERE TO HELP
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

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
    with st.chat_message(msg["role"]):
        st.write(msg["text"])

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
    st.session_state.messages.append({"role": "user", "text": user_input})
    with st.chat_message("user"):
        st.write(user_input)

    meta: dict = {}
    with st.chat_message("assistant"):
        full_text = st.write_stream(
            stream_agent(user_input, st.session_state.thread_id, meta)
        )

    st.session_state.messages.append({
        "role": "assistant",
        "text": full_text or "",
        "quick_replies": meta.get("quick_replies") or [],
    })
