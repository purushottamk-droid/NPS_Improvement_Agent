"""
output_schema.py — Agent 3: Risk & Scenario Classification Agent
"""

from pydantic import BaseModel, Field
from typing import List, Literal


class RenewalInfo(BaseModel):
    """Renewal-timing signal, used to drive the risk_level rules and the
    renewal/upsell signal logic in Section 3 of the prompt."""

    is_renewal_soon: bool = Field(
        description=(
            "True if the account's renewal is coming up within the "
            "configured threshold window (see the *_THRESHOLD_DAYS "
            "constants in prompt.py). Derived from opportunity close_date "
            "where opportunity type = Renewal, OR churn.next_renewal_date "
            "if no renewal opportunity exists yet."
        )
    )


class RiskClassification(BaseModel):
    """
    One classification result per account, matching prompt.py's current
    rule set (Sections 1-7).
    """

    account_id: str = Field(
        description="Salesforce Account ID — copy verbatim from account_context.account_id"
    )

    risk_level: Literal["High", "Upsell", "Low"] = Field(
        description=(
            "Follow the EXACT rule set in Section 4 of the prompt. Do not "
            "improvise new conditions."
        )
    )

    nps_label: Literal["Promoter", "Passive", "Detractor"] = Field(
        description="Copy verbatim from account_context.survey.label"
    )

    drivers: List[str] = Field(
        description=(
            "2-5 short, specific bullet reasons that justify the "
            "risk_level decided above. Each driver must cite a concrete "
            "signal from the input data (a score, a case subject, a "
            "sentiment value, a date) — never a vague statement like "
            "'customer seems unhappy'."
        )
    )

    renewal: RenewalInfo

    upsell_candidate: bool = Field(
        description=(
            "True only if this account qualifies for the Upsell path per "
            "Section 4's rules (Promoter + renewal due soon) OR the "
            "post-closed-won upsell/cross-sell trigger described in "
            "Section 3 of the prompt. False otherwise — including for "
            "every High or Low risk_level account."
        )
    )

    rep_performance_flag: bool = Field(
        default=False,
        description=(
            "True if this account's outcome (esp. Detractor label) "
            "appears linked to rep performance issues (per Section 1f). "
            "Requires Sales Rep Name on the opportunity — not currently "
            "present in the input. Defaults to False until that data "
            "exists."
        )
    )

    recommended_action: str = Field(
        description=(
            "ONE concrete, specific proactive action for this account — "
            "who should do what, by when. Never generic ('reach out to "
            "customer'). For Detractor/Passive accounts, must reflect "
            "the Detractor-to-Promoter recovery path from Section 2 of "
            "the prompt."
        )
    )


class RiskClassificationBatch(BaseModel):
    """
    Root-level structured output for Agent 3 (risk_classification_agent).
    Used directly as the LlmAgent's output_schema= — Gemini returns ALL
    account classifications for the run in this single wrapper, in one
    call.

    SCALE FLAG: see agent.py module docstring — if classifications count
    ever comes back short of account_context_list's length, that's the
    signal this single-call approach is hitting output truncation and
    needs to move to a per-account looped design instead.
    """

    classifications: List[RiskClassification] = Field(
        description=(
            "One RiskClassification per entry in account_context_list. "
            "Do not skip any."
        )
    )
