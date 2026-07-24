# Local Dev Guide — From Files to a Running Local Chat

Covers: getting Claude Code to actually build the agent from what's in this folder, testing it in a terminal, then wrapping it in a local browser chat. Everything here assumes local-only — no deployment, no hosting, no domain.

---

## 1. Get Claude Code building from these files

**Install Claude Code** (native installer is Anthropic's current recommended path, no Node.js required):
```bash
# macOS / Linux
curl -fsSL https://claude.ai/install.sh | bash

# Windows PowerShell
irm https://claude.ai/install.ps1 | iex
```
npm also works if you'd rather (`npm install -g @anthropic-ai/claude-code`, requires Node.js 18+) — same binary either way.

You'll need a Claude Pro, Max, Team, Enterprise, or Console (API-billed) account — the free Claude.ai plan doesn't include Claude Code access.

**Set up the project folder:**
```bash
mkdir atlas-dental-agent && cd atlas-dental-agent
git init
```
Drop in everything you've got so far:
```
atlas-dental-agent/
  CLAUDE.md
  plan.md
  test_cases.md
  schema.sql
  .env.example
  docs/
    dental_agent_unified_system_design_v3.md
    dental_agent_conversational_flow.md
    dental_agent_intake_design_v2.md
    dental_agent_intake_flow.mermaid
    dental_agent_system_architecture.mermaid
    dental_pricing_faq_knowledge_base.json
    atlas_dental_clinic_knowledge.md
    atlas_dental_vector_db_design.md
```

**Start Claude Code:**
```bash
claude
```
First run opens a browser to authenticate against your account. Claude Code auto-loads `CLAUDE.md` the moment you start a session in this directory — you don't need to paste it in.

**Kickoff prompt** — since `CLAUDE.md` and `plan.md` already carry the detail, keep this directive rather than re-explaining the project:

> Read CLAUDE.md and plan.md, then begin Phase 0. When you get to Phase 1, build `src/graph/runner.py` exactly as specified in plan.md's Phase 1 section — that's the function I'll be calling from a terminal script and a local chat UI.

From there, work through it like any Claude Code session: it'll propose file writes and commands, you review and approve (or let it run more autonomously if you're comfortable — your call). Commit after each phase so you've got checkpoints to `/rewind` to if a phase goes sideways.

---

## 2. Testing it in a terminal

Once Phase 1 is done, `invoke_agent()` exists and this is all you need:

```python
# cli.py — terminal test harness
import uuid
from src.graph.runner import invoke_agent

def main():
    thread_id = str(uuid.uuid4())
    print("Atlas Dental Agent (terminal test) — type 'exit' to quit\n")
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("exit", "quit"):
            break
        response = invoke_agent(user_input, thread_id)
        print(f"Agent: {response['text']}\n")
        if response.get("quick_replies"):
            print(f"  (suggested replies: {', '.join(response['quick_replies'])})\n")

if __name__ == "__main__":
    main()
```

Run with `python cli.py`.

**Why `thread_id` matters:** the memory checkpointer in Phase 1 uses it to keep the conversation's state alive across multiple calls. Without it, every message would land as a brand-new conversation with no memory of what came before — the agent would re-ask for your name every turn.

This terminal loop is genuinely enough to walk through every scenario in `test_cases.md` by hand before anything visual exists — worth doing that pass first, since it's the fastest way to catch a branching bug.

---

## 3. A local front-end chat

Given this runs on your machine for now, **Streamlit** is the fastest path to a real chat UI with minimal code:

```python
# app.py
import uuid
import streamlit as st
from src.graph.runner import invoke_agent

st.title("Atlas Dental — Agent (local test)")

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["text"])

if user_input := st.chat_input("Type a message..."):
    st.session_state.messages.append({"role": "user", "text": user_input})
    with st.chat_message("user"):
        st.write(user_input)

    response = invoke_agent(user_input, st.session_state.thread_id)
    st.session_state.messages.append({"role": "assistant", "text": response["text"]})
    with st.chat_message("assistant"):
        st.write(response["text"])
        if response.get("quick_replies"):
            cols = st.columns(len(response["quick_replies"]))
            for col, option in zip(cols, response["quick_replies"]):
                col.button(option)
```

```bash
pip install streamlit
streamlit run app.py
```

This opens a real chat window at `http://localhost:8501` — message bubbles, quick-reply buttons rendered from the `AgentResponse.quick_replies` field already designed in v2, and a conversation that persists for as long as your browser tab/session is open.

**Alternative (later, not now):** FastAPI backend + plain HTML/JS frontend. More setup, but it's the shape your eventual production architecture actually needs (a real API that a patient-facing widget, or the receptionist Web App, could call). Worth doing once you're past local testing — not a good use of time before that.

---

## 4. What "complete" means at this stage

A complete *local* chat, for where you are right now, means:
- The Streamlit UI can walk a full conversation — greeting → identity resolution → booking/registration/emergency branching → confirmation — with state correctly carried across every turn via `thread_id`.
- Side effects actually fire: a test Calendar event gets created, a test Gmail send goes out (point these at test accounts, not the real clinic accounts, until you trust the flow).

It does **not** yet mean: reachable by real patients, behind auth, on a real domain, talking to production Supabase. That's a separate, later phase — hosting and a production frontend — and nothing about this local setup blocks you from getting there later; it's the same `invoke_agent()` contract either way.

**Real milestone to aim for:** the Streamlit UI getting through Phase 2's test cases from `test_cases.md` correctly. That's "it's working," not Phase 0/1 finishing — those are just scaffolding.
