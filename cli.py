"""
cli.py — terminal test harness for the Atlas Dental agent.

Depends on src/agents/runner.py existing with an invoke_agent(message, thread_id)
function, per plan.md Phase 1. Run from the project root: python cli.py
"""
import uuid
from src.agents.runner import invoke_agent


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
