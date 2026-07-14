from google.adk.agents import SequentialAgent


from scripts.survey_and_account_context_agent import survey_and_account_context_agent  
from scripts.risk_classification_agent import risk_classification_agent                
from scripts.action_agent import action_agent                                          

root_agent = SequentialAgent(
    name="nps_improvement_pipeline",
    sub_agents=[
        survey_and_account_context_agent,   
        risk_classification_agent,          
        action_agent,                       
    ]
)