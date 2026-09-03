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


from agent_framework import WorkflowContext, executor
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import DefaultAzureCredential
from .prompt import RISK_CLASSIFICATION_PROMPT
from .output_schema import RiskClassificationBatch


chat_client = AzureOpenAIChatClient(credential=DefaultAzureCredential())
risk_agent = chat_client.as_agent(name="risk_classification_agent")


@executor(id="risk_classification")
async def classify_risk(nps_payload: dict, ctx: WorkflowContext[dict]) -> None:
    instructions_text = RISK_CLASSIFICATION_PROMPT(nps_payload)

    response = await risk_agent.run(
        instructions_text,
        response_format=RiskClassificationBatch,
        temperature=0.1,
    )
    result = response.value

    await ctx.set_shared_state("risk_classification_results", result)
    await ctx.send_message(result)