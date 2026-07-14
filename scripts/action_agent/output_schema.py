"""
scripts/action_agent/output_schema.py

Pydantic schema for the Action Agent output (merged Agent 4 + Agent 5).
"""

from pydantic import BaseModel, Field
from typing import List, Literal, Optional


class ActionRecord(BaseModel):
    """A single action taken (or skipped) by the Action Agent, for one account."""

    type: Literal["notify_manager", "message_rep"] = Field(
        description="Which action this record corresponds to"
    )

    status: Literal["SENT", "ERROR", "SKIPPED"] = Field(
        description=(
            "Outcome of the action. "
            "SENT = tool executed successfully. "
            "ERROR = tool call failed. "
            "SKIPPED = required session state value missing, OR account's "
            "risk_level is Low with no action needed."
        )
    )

    account_id: str = Field(description="Salesforce Account ID this action relates to")

    account_name: Optional[str] = Field(
        default=None,
        description="Account name, for readability in the audit trail"
    )

    reason: str = Field(
        description="One sentence — why this action was taken or skipped"
    )

    detail: Optional[str] = Field(
        default=None,
        description=(
            "Extra info about the executed action — e.g. Gmail message_id. "
            "Null if status is ERROR or SKIPPED."
        )
    )


class ActionResult(BaseModel):
    """Top-level output for the Action Agent."""

    actions: List[ActionRecord] = Field(
        default=[],
        description=(
            "One ActionRecord per rule evaluated, per account. Includes "
            "SKIPPED entries (e.g. Low-risk accounts, or missing email) "
            "so the full decision trail is auditable."
        )
    )
