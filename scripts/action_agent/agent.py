"""
scripts/action_agent/agent.py

Action Agent — Recommendation + Execution, Merged


"""

from google.adk.agents import LlmAgent

from .prompt import ACTION_PROMPT
from .tools import (
    notify_manager_tool,
    message_rep_tool,
)


action_agent = LlmAgent(

    name="action_agent",

    model="gemini-2.5-flash",

    instruction=ACTION_PROMPT,

    tools=[
        notify_manager_tool,
        message_rep_tool,
    ],

    output_key="actions_taken",
)
