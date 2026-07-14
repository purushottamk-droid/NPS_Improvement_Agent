"""
scripts/action_agent/agent.py

Action Agent — deterministic, rule-based, no LLM calls.

Both email SENDING and email content GENERATION are disabled for now —
this agent only applies the fixed risk_level rule (see RULE 0 below) and
emits one lightweight ActionRecord per account/tool-type for UI display.
Implemented as a plain BaseAgent (not an LlmAgent with tools) specifically
to avoid burning through Gemini quota: the previous tool-calling design
made one LLM turn per tool call per account, which exhausted the
project's rate limit at ~30 accounts. Pure Python has no such limit.

RULE 0 — WHICH ACCOUNTS GET ACTIONED (unchanged from the old prompt.py):
  Only accounts with risk_level "High" or "Upsell" get action records.
  Every "Low" risk account gets one SKIPPED record per tool type.

SESSION STATE:
  Reads  -> ctx.session.state["risk_classification_results"]
            ctx.session.state["rep_email"], ["manager_email"]
  Writes -> ctx.session.state["actions_taken"]
"""

from google.adk.agents import BaseAgent
from google.adk.events import Event

from .output_schema import ActionRecord, ActionResult


class ActionAgent(BaseAgent):
    async def _run_async_impl(self, ctx):
        classifications = ctx.session.state.get("risk_classification_results", {}).get("classifications", [])
        rep_email = ctx.session.state.get("rep_email")
        manager_email = ctx.session.state.get("manager_email")

        print(f"\n[ActionAgent] Evaluating {len(classifications)} classified account(s)")

        records: list[ActionRecord] = []

        for c in classifications:
            account_id = c.get("account_id")
            account_name = c.get("account_name") or account_id
            risk_level = c.get("risk_level")
            recommended_action = c.get("recommended_action") or ""

            if risk_level not in ("High", "Upsell"):
                for action_type in ("notify_manager", "message_rep"):
                    records.append(ActionRecord(
                        type=action_type,
                        status="SKIPPED",
                        account_id=account_id,
                        account_name=account_name,
                        reason="Low risk — no action needed",
                    ))
                continue

            if manager_email:
                records.append(ActionRecord(
                    type="notify_manager",
                    status="GENERATED",
                    account_id=account_id,
                    account_name=account_name,
                    reason=f"{risk_level} risk — {recommended_action}",
                    detail=recommended_action,
                ))
            else:
                records.append(ActionRecord(
                    type="notify_manager",
                    status="SKIPPED",
                    account_id=account_id,
                    account_name=account_name,
                    reason="manager_email missing from session state",
                ))

            if rep_email:
                records.append(ActionRecord(
                    type="message_rep",
                    status="GENERATED",
                    account_id=account_id,
                    account_name=account_name,
                    reason=f"{risk_level} risk — {recommended_action}",
                    detail=recommended_action,
                ))
            else:
                records.append(ActionRecord(
                    type="message_rep",
                    status="SKIPPED",
                    account_id=account_id,
                    account_name=account_name,
                    reason="rep_email missing from session state",
                ))

        result = ActionResult(actions=records)
        ctx.session.state["actions_taken"] = result.model_dump()

        print(f"[ActionAgent] {len(records)} action record(s) generated "
              f"({sum(1 for r in records if r.status == 'GENERATED')} GENERATED, "
              f"{sum(1 for r in records if r.status == 'SKIPPED')} SKIPPED)")

        yield Event(author=self.name, content=None)


action_agent = ActionAgent(name="action_agent")
