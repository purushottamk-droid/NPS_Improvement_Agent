"""
scripts/action_agent/agent.py

Action Agent — Recommendation + Execution, Merged


"""

import os

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
os.environ["GOOGLE_CLOUD_PROJECT"] = "atgeir-moae-dev"
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"



from google.adk.agents import LlmAgent
from google.genai import types

from .prompt import ACTION_PROMPT
from .tools import (
    notify_manager_tool,
    message_rep_tool,
)


action_agent = LlmAgent(

    name="action_agent",

    model="gemini-3.5-flash",

    instruction=ACTION_PROMPT,

    tools=[
        notify_manager_tool,
        message_rep_tool,
    ],

    generate_content_config=types.GenerateContentConfig(
        temperature=0.1,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    ),

    output_key="actions_taken",
)