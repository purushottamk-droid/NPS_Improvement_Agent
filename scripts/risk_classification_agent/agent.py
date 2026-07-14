"""
agent.py — Agent 3: Risk & Scenario Classification Agent

WHAT THIS AGENT DOES:
  Reads all account contexts from session state (written by the combined
  Agent 1). Sends ALL accounts to Gemini in ONE call.
  Gemini classifies every account (scenario + risk_level + drivers +
  recommended_action) and returns structured Pydantic output.
  Writes results to session state for Agent 4 to read.

SESSION STATE:
  Reads  -> ctx.session.state["account_context_list"] 
  Writes -> ctx.session.state["risk_classification_results"] 
"""

from google.adk.agents import LlmAgent
from .prompt import RISK_CLASSIFICATION_PROMPT
from .output_schema import RiskClassificationBatch


risk_classification_agent = LlmAgent(

    # Agent identity -- used by ADK pipeline to identify this agent
    name="risk_classification_agent",

    # Gemini model -- flash is fast and cost effective for this analysis
    model="gemini-2.5-flash-lite",

    # The crucial prompt -- tells Gemini exactly how to classify each
    # account. Gemini reads account_context_list from session state
    # automatically. Full prompt logic is in prompt.py
    instruction=RISK_CLASSIFICATION_PROMPT,

    # Pydantic schema -- Gemini MUST return output matching this structure
    # RiskClassificationBatch contains list of RiskClassification --
    # one result per account -- even though it is one Gemini call
    # Defined in output_schema.py
    output_schema=RiskClassificationBatch,

    # Where LlmAgent writes the result in session state
    # Agent 4 reads ctx.session.state["risk_classification_results"]
    output_key="risk_classification_results",

    # Exclude conversation history from Gemini API call -- sends only
    # the current instruction + input, reducing token size and latency
    include_contents='none',
)
