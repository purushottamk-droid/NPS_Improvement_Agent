from google.adk.agents import SequentialAgent


from scripts.nps_data_collection_agent.agent import NpsAccountContextAgent
from scripts.risk_classification_agent import risk_classification_agent                
from scripts.action_agent import action_agent                                          

root_agent = SequentialAgent(
    name="nps_improvement_pipeline",
    sub_agents=[
        NpsAccountContextAgent(name="nps_data_collection_agent"),
        risk_classification_agent,          
        action_agent,                       
    ]
)


# import time
# from google.adk.agents import SequentialAgent
# from google.adk.agents.callback_context import CallbackContext
# from google.genai import types
# from scripts.nps_data_collection_agent.agent import NpsAccountContextAgent
# from scripts.risk_classification_agent import risk_classification_agent
# from scripts.action_agent import action_agent

# _timings = {}

# def make_before(name):
#     def _before(callback_context: CallbackContext):
#         _timings[name] = {"start": time.perf_counter()}
#     return _before

# def make_after(name):
#     def _after(callback_context: CallbackContext):
#         _timings[name]["end"] = time.perf_counter()
#         _timings[name]["duration"] = _timings[name]["end"] - _timings[name]["start"]
#         print(f"[TIMING] {name}: {_timings[name]['duration']:.2f}s")
#     return _after

# nps_agent = NpsAccountContextAgent(name="nps_data_collection_agent")
# nps_agent.before_agent_callback = make_before("nps_data_collection_agent")
# nps_agent.after_agent_callback = make_after("nps_data_collection_agent")

# risk_classification_agent.before_agent_callback = make_before("risk_classification_agent")
# risk_classification_agent.after_agent_callback = make_after("risk_classification_agent")

# action_agent.before_agent_callback = make_before("action_agent")
# action_agent.after_agent_callback = make_after("action_agent")

# root_agent = SequentialAgent(
#     name="nps_improvement_pipeline",
#     sub_agents=[nps_agent, risk_classification_agent, action_agent],
# )