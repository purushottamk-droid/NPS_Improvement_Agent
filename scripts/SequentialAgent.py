from google.adk.agents import SequentialAgent


from scripts.nps_data_collection_agent.agent import nps_data_collection_agent
from scripts.risk_classification_agent import risk_classification_agent                
from scripts.action_agent import action_agent                                          

root_agent = SequentialAgent(
    name="nps_improvement_pipeline",
    sub_agents=[
        nps_data_collection_agent,   
        risk_classification_agent,          
        action_agent,                       
    ]
)