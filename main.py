"""
main.py — Run the full NPS Improvement Agent pipeline
"""
from dotenv import load_dotenv
load_dotenv()
import time
import asyncio
from google.adk.runners import InMemoryRunner
from google.genai import types

from scripts.SequentialAgent import root_agent


async def run():
    runner = InMemoryRunner(
        agent=root_agent,
        app_name="nps_improvement_pipeline",
    )

    session = await runner.session_service.create_session(
        app_name="nps_improvement_pipeline",
        user_id="test_user",
        state={
            "rep_email": "kakadetalent@gmail.com",     
            "manager_email": "kakade007k@gmail.com",   
        }
    )

    print(f"\n── Running NPS Improvement pipeline ──\n")

    start_time = time.time()
    agent_times = {}
    current_agent = None
    current_agent_start = None

    async for event in runner.run_async(
        user_id="test_user",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text="start")]),
    ):
        print(f"[{event.author}]", end=" ")

        now = time.time()
        if event.author != current_agent:
            if current_agent is not None:
                agent_times[current_agent] = now - current_agent_start
            current_agent = event.author
            current_agent_start = now
        print(f"invocation_id: {event.invocation_id}")

        if event.content and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    print(part.text)

                fr = getattr(part, "function_response", None)
                if fr:
                    resp = fr.response or {}
                    print(f"\n{'─'*60}")
                    print(f"  ACTION EXECUTED: {fr.name}")
                    print(f"{'─'*60}")
                    print(f"  Status       : {resp.get('status')}")
                    if resp.get("account_name"):
                        print(f"  Account      : {resp.get('account_name')} ({resp.get('account_id')})")
                    if resp.get("rep_email"):
                        print(f"  To (Rep)     : {resp.get('rep_email')}")
                    if resp.get("manager_email"):
                        print(f"  To (Manager) : {resp.get('manager_email')}")
                    if resp.get("subject"):
                        print(f"  Subject      : {resp.get('subject')}")
                    if resp.get("message_id"):
                        print(f"  Message ID   : {resp.get('message_id')}")
                    if resp.get("error_message"):
                        print(f"  ERROR        : {resp.get('error_message')}")
                    print(f"{'─'*60}\n")

    if current_agent is not None:
        agent_times[current_agent] = time.time() - current_agent_start

    end_time = time.time()
    print(f"\n⏱  Total pipeline time: {end_time - start_time:.2f} seconds")
    print("\n⏱  Per-agent duration:")
    for author, duration in agent_times.items():
        print(f"    {author}: {duration:.2f}s")

    print("\n── Pipeline finished ──\n")


if __name__ == "__main__":
    asyncio.run(run())