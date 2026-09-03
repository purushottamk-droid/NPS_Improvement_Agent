"""
scripts/action_agent/agent.py

Action Agent — Recommendation + Execution, Merged


"""




from agent_framework import WorkflowContext, executor
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import DefaultAzureCredential

from .prompt import ACTION_PROMPT
from .tools import (
    notify_manager_tool,
    message_rep_tool,
)


chat_client = AzureOpenAIChatClient(credential=DefaultAzureCredential())
action_agent = chat_client.as_agent(
    name="action_agent",
    tools=[notify_manager, message_rep],   # decorated in tools.py — see below
)


@executor(id="action_agent")
async def take_actions(risk_classification_results: dict, ctx: WorkflowContext[dict]) -> None:
    nps_payload = await ctx.get_shared_state("nps_payload")   # NOT from the chain — pulled from shared state
    instructions_text = ACTION_PROMPT(risk_classification_results, nps_payload)

    response = await action_agent.run(instructions_text, temperature=0.1)
    result = response.text   # prompt still instructs "return ONLY JSON" — parsed downstream if needed

    await ctx.set_shared_state("actions_taken", result)
    await ctx.send_message(result)