import os
os.environ["GOOGLE_CLOUD_PROJECT"] = "atgeir-moae-dev"
os.environ["GOOGLE_CLOUD_LOCATION"] = "us-central1"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "1"

import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.genai import types

# Import the NPS agent we built
# (If you wrapped this in SequentialAgent.py, change this to: from scripts.SequentialAgent import root_agent)
from scripts.SequentialAgent import root_agent

# ─────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────

api = FastAPI(title="NPS Improvement Agent — SSE API")

api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Update this with your frontend URLs in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

session_service = InMemorySessionService()



runner = Runner(
    agent=root_agent,
    app_name="nps_pipeline",
    session_service=session_service,
)


# ─────────────────────────────────────────────
# Request schemas
# ─────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    user_id: str
    # BATCH MODE: No other inputs (like account_id or date) are required yet.
    # When you move to single-account triggers, add account_id here.


class RunRequest(BaseModel):
    user_id: str
    session_id: str


# ─────────────────────────────────────────────
# Helper — SSE formatter
# ─────────────────────────────────────────────

def sse(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"


async def stream_events(event_gen, user_id, session_id):
    """
    Stream all agent events as SSE, ending with the complete payload.
    """
    last_author = "NpsAccountContextAgent"
    try:
        # 1. Yield all progress events as they happen
        async for event in event_gen:
            text = ""
            if event.content and event.content.parts:
                text = "".join(
                    p.text for p in event.content.parts
                    if hasattr(p, "text") and p.text
                )

            last_author = event.author

            # Note: We ONLY yield the progress event inside the loop now
            yield sse("progress", {
                "author": event.author,
                "id":     event.id,
                "text":   text,
            })

        # 2. THE LOOP IS FINISHED. 
        # The ADK runner has now safely committed the final state to memory!
        session = await runner.session_service.get_session(
            app_name="nps_pipeline",
            user_id=user_id,
            session_id=session_id,
        )
        
        nps_payload = session.state.get("nps_payload") if session else None
        risk_results = session.state.get("risk_classification_results") if session else None
        actions_taken = session.state.get("actions_taken") if session else None

        yield sse("done", {
            "author": last_author,
            "text": "",
            "nps_payload": nps_payload,
            "risk_classification_results": risk_results,
            "actions_taken": actions_taken,
        })

    except Exception as e:
        import logging
        logging.error(f"Error in stream_events: {str(e)}", exc_info=True)
        yield sse("error", {"message": str(e)})

# ─────────────────────────────────────────────
# ENDPOINT 1 — Health check
# ─────────────────────────────────────────────

@api.get("/health")
async def healthz():
    """Confirm the server is alive."""
    return {"status": "ok"}


# ─────────────────────────────────────────────
# ENDPOINT 2 — Create a session
# ─────────────────────────────────────────────

@api.post("/agent/sessions")
async def create_session(req: CreateSessionRequest):
    """
    Creates a fresh session for the NPS pipeline.
    """
    session = await session_service.create_session(
        app_name="nps_pipeline",
        user_id=req.user_id,
        state={},
    )
    return {
        "session_id":    session.id,
        "user_id":       req.user_id,
        "initial_state": session.state,
    }


# ─────────────────────────────────────────────
# ENDPOINT 3 — Run the full pipeline
# ─────────────────────────────────────────────

@api.post("/agent/run")
async def run_agent(req: RunRequest):
    """
    Runs the NPS data collection pipeline and streams live progress.
    The final 'done' event contains the complete nps_payload.
    """
    content = types.Content(role="user", parts=[types.Part(text="start")])

    event_gen = runner.run_async(
        user_id=req.user_id,
        session_id=req.session_id,
        new_message=content,
        run_config=RunConfig(streaming_mode=StreamingMode.SSE),
    )

    return StreamingResponse(
        stream_events(event_gen, req.user_id, req.session_id), 
        media_type="text/event-stream"
    )


# ─────────────────────────────────────────────
# ENDPOINT 4 — Get final pipeline result
# ─────────────────────────────────────────────

@api.get("/agent/result/{session_id}")
async def get_result(session_id: str, user_id: str):
    """
    Returns the final NPS payload (summary + account contexts).
    Call this AFTER you receive event: done from /agent/run.
    """
    session = await session_service.get_session(
        app_name="nps_pipeline",
        user_id=user_id,
        session_id=session_id,
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session_id,
        "nps_payload": session.state.get("nps_payload"),
        "risk_classification_results": session.state.get("risk_classification_results"),
        "actions_taken": session.state.get("actions_taken"),
    }