"""
main.py — Run the full NPS Improvement Agent pipeline
"""
from dotenv import load_dotenv
load_dotenv()
import time
import asyncio
from google.adk.runners import InMemoryRunner
from google.genai import types

from scripts.SequentialAgent import root_agent


async def run():
    runner = InMemoryRunner(
        agent=root_agent,
        app_name="nps_improvement_pipeline",
    )

    session = await runner.session_service.create_session(
        app_name="nps_improvement_pipeline",
        user_id="test_user",
        state={
            "rep_email": "kakadetalent@gmail.com",     
            "manager_email": "kakade007k@gmail.com",
            "nps_payload":{
        "summary": {
            "total_responses": 5,
            "promoters_count": 4,
            "passives_count": 0,
            "detractors_count": 1,
            "promoters_pct": 80.0,
            "passives_pct": 0.0,
            "detractors_pct": 20.0,
            "nps_value": 60.0
        },
        "account_contexts": [
            {
            "account_id": "001fj00001QbtDAAAZ",
            "account_name": "Jasper Health",
            "survey": {
                "response_id": 780097,
                "type": "ongoing",
                "score": 9,
                "label": "Promoter",
                "date": "2026-06-24T15:23:00+00:00",
                "comment": "The platform is reliable and the customer success team has been proactive. We are seeing clear value from the rollout."
            },
            "churn": {
                "is_active": True,
                "is_churn_account": False,
                "tenure_in_days": 436,
                "primary_churn_score_value": 95.0,
                "next_renewal_date": "2026-03-03T00:00:00+00:00"
            },
            "opportunities": {
                "latest_closed_won_date": "2025-09-04",
                "open_opportunities": []
            },
            "cases": {
                "open_cases": [],
                "has_open_high_priority": False,
                "latest_case_reason": None
            },
            "gong": {
                "recent_calls_count": 0,
                "recent_sentiment": None
            }
            },
            {
            "account_id": "001fj00001QbtDTAAZ",
            "account_name": "Meridian Foods",
            "survey": {
                "response_id": 780633,
                "type": "ongoing",
                "score": 10,
                "label": "Promoter",
                "date": "2026-06-24T10:18:00+00:00",
                "comment": "Overall experience has been strong. We would recommend the platform to similar teams."
            },
            "churn": {
                "is_active": True,
                "is_churn_account": False,
                "tenure_in_days": 393,
                "primary_churn_score_value": 95.0,
                "next_renewal_date": "2026-04-12T00:00:00+00:00"
            },
            "opportunities": {
                "latest_closed_won_date": "2025-10-05",
                "open_opportunities": []
            },
            "cases": {
                "open_cases": [],
                "has_open_high_priority": False,
                "latest_case_reason": None
            },
            "gong": {
                "recent_calls_count": 0,
                "recent_sentiment": None
            }
            },
            {
            "account_id": "001fj00001QcFRVAA3",
            "account_name": "Jasper Utilities",
            "survey": {
                "response_id": 780596,
                "type": "ongoing",
                "score": 0,
                "label": "Detractor",
                "date": "2026-06-23T16:35:00+00:00",
                "comment": "Support response has been slow and we still have unresolved issues from the last escalation."
            },
            "churn": {
                "is_active": True,
                "is_churn_account": False,
                "tenure_in_days": 30,
                "primary_churn_score_value": 18.0,
                "next_renewal_date": "2027-11-09T00:00:00+00:00"
            },
            "opportunities": {
                "latest_closed_won_date": None,
                "open_opportunities": [
                {
                    "opportunity_id": "006DMO000000000100215",
                    "name": "Jasper Utilities - Quality Management - 2026 Cross-sell",
                    "stage_name": "Lost No Decision",
                    "next_step": None,
                    "type": "3 - Cross-sell",
                    "deal_value_arr": 120235.0,
                    "risks": "Executive sponsor not yet confirmed",
                    "cbi_raw_text": "Increase operational efficiency",
                    "opportunity_manager_notes": "Aiden Murphy owns next step. Primary focus is reduced manual reporting."
                },
                {
                    "opportunity_id": "006DMO000000000100192",
                    "name": "Jasper Utilities - Permit Control - 2026 Cross-sell",
                    "stage_name": "Demo",
                    "next_step": None,
                    "type": "3 - Cross-sell",
                    "deal_value_arr": 48371.0,
                    "risks": "Executive sponsor not yet confirmed",
                    "cbi_raw_text": "Increase operational efficiency",
                    "opportunity_manager_notes": "Chloe Martin owns next step. Primary focus is faster audit readiness."
                }
                ]
            },
            "cases": {
                "open_cases": [],
                "has_open_high_priority": False,
                "latest_case_reason": None
            },
            "gong": {
                "recent_calls_count": 0,
                "recent_sentiment": None
            }
            },
            {
            "account_id": "001fj00001QbtCpAAJ",
            "account_name": "Redwood Utilities",
            "survey": {
                "response_id": 780624,
                "type": "ongoing",
                "score": 9,
                "label": "Promoter",
                "date": "2026-06-23T11:04:00+00:00",
                "comment": "The platform is reliable and the customer success team has been proactive. We are seeing clear value from the rollout."
            },
            "churn": {
                "is_active": True,
                "is_churn_account": False,
                "tenure_in_days": 497,
                "primary_churn_score_value": 94.0,
                "next_renewal_date": "2025-10-30T00:00:00+00:00"
            },
            "opportunities": {
                "latest_closed_won_date": "2025-04-28",
                "open_opportunities": []
            },
            "cases": {
                "open_cases": [],
                "has_open_high_priority": False,
                "latest_case_reason": None
            },
            "gong": {
                "recent_calls_count": 0,
                "recent_sentiment": None
            }
            },
            {
            "account_id": "001fj00001QbtDDAAZ",
            "account_name": "Vertex Pharma",
            "survey": {
                "response_id": 780627,
                "type": "ongoing",
                "score": 10,
                "label": "Promoter",
                "date": "2026-06-22T16:14:00+00:00",
                "comment": "Overall experience has been strong. We would recommend the platform to similar teams."
            },
            "churn": {
                "is_active": True,
                "is_churn_account": False,
                "tenure_in_days": 438,
                "primary_churn_score_value": 92.0,
                "next_renewal_date": "2026-05-16T00:00:00+00:00"
            },
            "opportunities": {
                "latest_closed_won_date": "2025-07-22",
                "open_opportunities": []
            },
            "cases": {
                "open_cases": [],
                "has_open_high_priority": False,
                "latest_case_reason": None
            },
            "gong": {
                "recent_calls_count": 0,
                "recent_sentiment": None
            }
            }
        ]
        }   
                }
            )

    print(f"\n── Running NPS Improvement pipeline ──\n")

    start_time = time.time()
    agent_times = {}
    current_agent = None
    current_agent_start = None

    async for event in runner.run_async(
        user_id="test_user",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text="start")]),
    ):
        print(f"[{event.author}]", end=" ")

        now = time.time()
        if event.author != current_agent:
            if current_agent is not None:
                agent_times[current_agent] = now - current_agent_start
            current_agent = event.author
            current_agent_start = now
        print(f"invocation_id: {event.invocation_id}")

        if event.content and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    print(part.text)

                fr = getattr(part, "function_response", None)
                if fr:
                    resp = fr.response or {}
                    print(f"\n{'─'*60}")
                    print(f"  ACTION EXECUTED: {fr.name}")
                    print(f"{'─'*60}")
                    print(f"  Status       : {resp.get('status')}")
                    if resp.get("account_name"):
                        print(f"  Account      : {resp.get('account_name')} ({resp.get('account_id')})")
                    if resp.get("rep_email"):
                        print(f"  To (Rep)     : {resp.get('rep_email')}")
                    if resp.get("manager_email"):
                        print(f"  To (Manager) : {resp.get('manager_email')}")
                    if resp.get("subject"):
                        print(f"  Subject      : {resp.get('subject')}")
                    if resp.get("message_id"):
                        print(f"  Message ID   : {resp.get('message_id')}")
                    if resp.get("error_message"):
                        print(f"  ERROR        : {resp.get('error_message')}")
                    print(f"{'─'*60}\n")

    if current_agent is not None:
        agent_times[current_agent] = time.time() - current_agent_start

    end_time = time.time()
    print(f"\n⏱  Total pipeline time: {end_time - start_time:.2f} seconds")
    print("\n⏱  Per-agent duration:")
    for author, duration in agent_times.items():
        print(f"    {author}: {duration:.2f}s")

    print("\n── Pipeline finished ──\n")


if __name__ == "__main__":
    asyncio.run(run())

# """
# main.py — TEST RUN with dummy data (2 reps x 3 accounts each)

# This bypasses NpsAccountContextAgent (Agent 1+2) on purpose — it would
# overwrite our seeded nps_payload with a real BigQuery fetch. This test
# pipeline runs ONLY risk_classification_agent -> action_agent, against
# the hand-built dummy data below.

# rep_id / rep_name / rep_email are attached PER ACCOUNT (inside each
# account_context, right after account_id/account_name) — this is the
# shape Agent 2 (NpsAccountContextAgent) will need to produce in real
# output, once rep info is wired into its Salesforce MCP opportunity
# lookups. manager_email stays a single session-state value, unchanged.
# """
# from dotenv import load_dotenv
# load_dotenv()
# import time
# import asyncio
# from google.adk.agents import SequentialAgent
# from google.adk.runners import InMemoryRunner
# from google.genai import types
# from scripts.SequentialAgent import root_agent

# from scripts.risk_classification_agent import risk_classification_agent
# from scripts.action_agent import action_agent





# # ─────────────────────────────────────────────
# # DUMMY nps_payload — 2 reps, 3 accounts each
# # (Promoter / Passive / Detractor per rep)
# # ─────────────────────────────────────────────
# DUMMY_NPS_PAYLOAD = {
#     "summary": {
#         "total_responses": 6,
#         "promoters_count": 2,
#         "passives_count": 2,
#         "detractors_count": 2,
#         "promoters_pct": 33.3,
#         "passives_pct": 33.3,
#         "detractors_pct": 33.3,
#         "nps_value": 0.0,
#     },
#     "account_contexts": [

#         # ── REP 1: Aiden Murphy ──────────────────────────────────
#         {
#             "account_id": "001fj00001QAcct001",
#             "account_name": "Jasper Health",
#             "rep_id": "005DMO000000000300010",
#             "rep_name": "Aiden Murphy",
#             "rep_email": "kakadetalent@gmail.com",
#             "manager_name": "Priya Shah",
#             "manager_email": "kakade007k@gmail.com",
#             "survey": {
#                 "response_id": 900001,
#                 "type": "ongoing",
#                 "score": 9,
#                 "label": "Promoter",
#                 "date": "2026-06-24T15:23:00+00:00",
#                 "comment": "The platform is reliable and the customer success team has been proactive.",
#             },
#             "churn": {
#                 "is_active": True,
#                 "is_churn_account": False,
#                 "tenure_in_days": 436,
#                 "primary_churn_score_value": 95.0,
#                 "next_renewal_date": "2026-09-03T00:00:00+00:00",
#             },
#             "opportunities": {
#                 "latest_closed_won_date": "2025-09-04",
#                 "open_opportunities": [],
#             },
#             "cases": {
#                 "open_cases": [],
#                 "has_open_high_priority": False,
#                 "latest_case_reason": None,
#             },
#             "gong": {
#                 "recent_calls_count": 0,
#                 "recent_sentiment": None,
#             },
#         },
#         {
#             "account_id": "001fj00001QAcct002",
#             "account_name": "Meridian Foods",
#             "rep_id": "005DMO000000000300010",
#             "rep_name": "Aiden Murphy",
#             "rep_email": "kakadetalent@gmail.com",
#             "manager_name": "Priya Shah",
#             "manager_email": "kakade007k@gmail.com",
#             "survey": {
#                 "response_id": 900002,
#                 "type": "ongoing",
#                 "score": 7,
#                 "label": "Passive",
#                 "date": "2026-06-24T10:18:00+00:00",
#                 "comment": "Experience is acceptable, though some workflows require additional configuration.",
#             },
#             "churn": {
#                 "is_active": True,
#                 "is_churn_account": False,
#                 "tenure_in_days": 393,
#                 "primary_churn_score_value": 70.0,
#                 "next_renewal_date": "2026-10-12T00:00:00+00:00",
#             },
#             "opportunities": {
#                 "latest_closed_won_date": "2025-10-05",
#                 "open_opportunities": [],
#             },
#             "cases": {
#                 "open_cases": [],
#                 "has_open_high_priority": False,
#                 "latest_case_reason": None,
#             },
#             "gong": {
#                 "recent_calls_count": 1,
#                 "recent_sentiment": "Neutral",
#             },
#         },
#         {
#             "account_id": "001fj00001QAcct003",
#             "account_name": "Jasper Utilities",
#             "rep_id": "005DMO000000000300010",
#             "rep_name": "Aiden Murphy",
#             "rep_email": "kakadetalent@gmail.com",
#             "manager_name": "Priya Shah",
#             "manager_email": "kakade007k@gmail.com",
#             "survey": {
#                 "response_id": 900003,
#                 "type": "ongoing",
#                 "score": 0,
#                 "label": "Detractor",
#                 "date": "2026-06-23T16:35:00+00:00",
#                 "comment": "Support response has been slow and we still have unresolved issues from the last escalation.",
#             },
#             "churn": {
#                 "is_active": True,
#                 "is_churn_account": False,
#                 "tenure_in_days": 30,
#                 "primary_churn_score_value": 18.0,
#                 "next_renewal_date": "2027-11-09T00:00:00+00:00",
#             },
#             "opportunities": {
#                 "latest_closed_won_date": None,
#                 "open_opportunities": [
#                     {
#                         "opportunity_id": "006DMO000000000100215",
#                         "name": "Jasper Utilities - Quality Management - 2026 Cross-sell",
#                         "stage_name": "Demo",
#                         "next_step": None,
#                         "type": "3 - Cross-sell",
#                         "deal_value_arr": 120235.0,
#                         "risks": "Executive sponsor not yet confirmed",
#                         "cbi_raw_text": "Increase operational efficiency",
#                         "opportunity_manager_notes": "Aiden Murphy owns next step. Primary focus is reduced manual reporting.",
#                     },
#                 ],
#             },
#             "cases": {
#                 "open_cases": [
#                     {
#                         "case_id": "500DMO0000001",
#                         "status": "Open",
#                         "reason": "Performance Issue",
#                         "subject": "Slow response time on reporting module",
#                         "priority": "High",
#                         "severity": "High",
#                         "is_closed": False,
#                         "is_escalated": True,
#                         "root_cause": None,
#                         "customer_sentiment": "Negative",
#                         "nps_risk_level": "High",
#                         "nps_risk_reason": "Unresolved escalation tied directly to Detractor score",
#                         "recommended_agent_action": "Escalate to support lead and schedule a call this week",
#                         "date_time": "2026-06-20T09:00:00+00:00",
#                     }
#                 ],
#                 "has_open_high_priority": True,
#                 "latest_case_reason": "Performance Issue",
#             },
#             "gong": {
#                 "recent_calls_count": 1,
#                 "recent_sentiment": "Negative",
#             },
#         },

#         # ── REP 2: Chloe Martin ──────────────────────────────────
#         {
#             "account_id": "001fj00001QAcct004",
#             "account_name": "Vertex Pharma",
#             "rep_id": "005DMO000000000300020",
#             "rep_name": "Chloe Martin",
#             "rep_email": "kakadetalent@gmail.com",
#             "manager_name": "Purushottam kakade",
#             "manager_email": "pukakade2018@gmail.com",
#             "survey": {
#                 "response_id": 900004,
#                 "type": "ongoing",
#                 "score": 10,
#                 "label": "Promoter",
#                 "date": "2026-06-22T16:14:00+00:00",
#                 "comment": "Overall experience has been strong. We would recommend the platform to similar teams.",
#             },
#             "churn": {
#                 "is_active": True,
#                 "is_churn_account": False,
#                 "tenure_in_days": 438,
#                 "primary_churn_score_value": 92.0,
#                 "next_renewal_date": "2026-08-16T00:00:00+00:00",
#             },
#             "opportunities": {
#                 "latest_closed_won_date": "2025-07-22",
#                 "open_opportunities": [],
#             },
#             "cases": {
#                 "open_cases": [],
#                 "has_open_high_priority": False,
#                 "latest_case_reason": None,
#             },
#             "gong": {
#                 "recent_calls_count": 0,
#                 "recent_sentiment": None,
#             },
#         },
#         {
#             "account_id": "001fj00001QAcct005",
#             "account_name": "Redwood Utilities",
#             "rep_id": "005DMO000000000300020",
#             "rep_name": "Chloe Martin",
#             "rep_email": "kakadetalent@gmail.com",
#             "manager_name": "Purushottam kakade",
#             "manager_email": "pukakade2018@gmail.com",
#             "survey": {
#                 "response_id": 900005,
#                 "type": "ongoing",
#                 "score": 8,
#                 "label": "Passive",
#                 "date": "2026-06-23T11:04:00+00:00",
#                 "comment": "Good overall, but onboarding took longer than expected.",
#             },
#             "churn": {
#                 "is_active": True,
#                 "is_churn_account": False,
#                 "tenure_in_days": 497,
#                 "primary_churn_score_value": 75.0,
#                 "next_renewal_date": "2026-11-30T00:00:00+00:00",
#             },
#             "opportunities": {
#                 "latest_closed_won_date": "2025-04-28",
#                 "open_opportunities": [],
#             },
#             "cases": {
#                 "open_cases": [],
#                 "has_open_high_priority": False,
#                 "latest_case_reason": None,
#             },
#             "gong": {
#                 "recent_calls_count": 1,
#                 "recent_sentiment": "Neutral",
#             },
#         },
#         {
#             "account_id": "001fj00001QAcct006",
#             "account_name": "Orion Infrastructure",
#             "rep_id": "005DMO000000000300020",
#             "rep_name": "Chloe Martin",
#             "rep_email": "kakadetalent@gmail.com",
#             "manager_name": "Purushottam kakade",
#             "manager_email": "pukakade2018@gmail.com",
#             "survey": {
#                 "response_id": 900006,
#                 "type": "ongoing",
#                 "score": 3,
#                 "label": "Detractor",
#                 "date": "2026-06-21T14:00:00+00:00",
#                 "comment": "Several required capabilities are missing from our workflow, so the team is evaluating alternatives.",
#             },
#             "churn": {
#                 "is_active": True,
#                 "is_churn_account": True,
#                 "tenure_in_days": 210,
#                 "primary_churn_score_value": 88.0,
#                 "next_renewal_date": "2026-09-25T00:00:00+00:00",
#             },
#             "opportunities": {
#                 "latest_closed_won_date": None,
#                 "open_opportunities": [],
#             },
#             "cases": {
#                 "open_cases": [
#                     {
#                         "case_id": "500DMO0000002",
#                         "status": "Open",
#                         "reason": "Feature Gap",
#                         "subject": "Missing workflow automation capability",
#                         "priority": "Medium",
#                         "severity": "Medium",
#                         "is_closed": False,
#                         "is_escalated": False,
#                         "root_cause": "Product gap",
#                         "customer_sentiment": "Negative",
#                         "nps_risk_level": "High",
#                         "nps_risk_reason": "Customer actively evaluating alternatives due to missing capability",
#                         "recommended_agent_action": "Loop in Product for gap assessment; propose interim workaround",
#                         "date_time": "2026-06-18T09:00:00+00:00",
#                     }
#                 ],
#                 "has_open_high_priority": False,
#                 "latest_case_reason": "Feature Gap",
#             },
#             "gong": {
#                 "recent_calls_count": 1,
#                 "recent_sentiment": "Negative",
#             },
#         },
#     ],
# }


# async def run():
#     runner = InMemoryRunner(
#         agent=root_agent,
#         app_name="nps_improvement_pipeline_test",
#     )

#     session = await runner.session_service.create_session(
#         app_name="nps_improvement_pipeline_test",
#         user_id="test_user",
#         state={
#             # rep_email is now PER-ACCOUNT (inside nps_payload) — not here.
#             "manager_email": "kakade007k@gmail.com",
#             "nps_payload": DUMMY_NPS_PAYLOAD,
#         }
#     )

#     print(f"\n── Running NPS Improvement pipeline (TEST — dummy data) ──\n")

#     start_time = time.time()
#     agent_times = {}
#     current_agent = None
#     current_agent_start = None

#     try:
#         async for event in runner.run_async(
#             user_id="test_user",
#             session_id=session.id,
#             new_message=types.Content(role="user", parts=[types.Part(text="start")]),
#         ):
#             print(f"[{event.author}]", end=" ")

#         now = time.time()
#         if event.author != current_agent:
#             if current_agent is not None:
#                 agent_times[current_agent] = now - current_agent_start
#             current_agent = event.author
#             current_agent_start = now
#         print(f"invocation_id: {event.invocation_id}")

#         if event.content and event.content.parts:
#             for part in event.content.parts:
#                 if hasattr(part, "text") and part.text:
#                     print(part.text)

#                 fr = getattr(part, "function_response", None)
#                 if fr:
#                     resp = fr.response or {}
#                     print(f"\n{'─'*60}")
#                     print(f"  ACTION EXECUTED: {fr.name}")
#                     print(f"{'─'*60}")
#                     print(f"  Status       : {resp.get('status')}")
#                     if resp.get("account_name"):
#                         print(f"  Account      : {resp.get('account_name')} ({resp.get('account_id')})")
#                     if resp.get("rep_email"):
#                         print(f"  To (Rep)     : {resp.get('rep_email')}")
#                     if resp.get("manager_email"):
#                         print(f"  To (Manager) : {resp.get('manager_email')}")
#                     if resp.get("subject"):
#                         print(f"  Subject      : {resp.get('subject')}")
#                     if resp.get("message_id"):
#                         print(f"  Message ID   : {resp.get('message_id')}")
#                     if resp.get("error_message"):
#                         print(f"  ERROR        : {resp.get('error_message')}")
#                     print(f"{'─'*60}\n")
#         else:
#             print(f"  (EMPTY CONTENT — author={event.author}, "
#                   f"error_code={getattr(event, 'error_code', None)}, "
#                   f"error_message={getattr(event, 'error_message', None)}, "
#                   f"partial={getattr(event, 'partial', None)}, "
#                   f"turn_complete={getattr(event, 'turn_complete', None)}, "
#                   f"actions={getattr(event, 'actions', None)})")

#     except Exception as e:
#         import traceback
#         print(f"\n{'='*60}")
#         print(f"  EXCEPTION DURING PIPELINE RUN: {type(e).__name__}: {e}")
#         print(f"{'='*60}")
#         traceback.print_exc()

#     if current_agent is not None:
#         agent_times[current_agent] = time.time() - current_agent_start

#     end_time = time.time()
#     print(f"\n⏱  Total pipeline time: {end_time - start_time:.2f} seconds")
#     print("\n⏱  Per-agent duration:")
#     for author, duration in agent_times.items():
#         print(f"    {author}: {duration:.2f}s")

#     print("\n── Pipeline finished ──\n")


# if __name__ == "__main__":
#     asyncio.run(run())



