from agent_framework import WorkflowBuilder

from scripts.nps_data_collection_agent.agent import collect_nps_data
# from scripts.risk_classification_agent.agent import classify_risk
# from scripts.action_agent.agent import take_actions

workflow = (
    WorkflowBuilder(start_executor=collect_nps_data)
    # .add_edge(collect_nps_data, classify_risk)
    # .add_edge(classify_risk, take_actions)
    .build()
)

