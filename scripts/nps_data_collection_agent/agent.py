"""
scripts/nps_account_context_agent/agent.py

Merged Agent — combines the original Agent 1 (Survey Ingestion & NPS Label)
and Agent 2 (Account Context Aggregation) into one custom ADK agent.

Input  (session state): none required yet — BATCH MODE.
    Pulls the entire churnzero_survey_response_data table on every run (no
    account_id / date filter). Once a real trigger/input is defined
    (single account_id, date-range watermark, etc.), swap the WHERE clause
    in _fetch_survey_responses_sync — nothing else changes.

Output (session state):
    nps_account_contexts → list[dict], one entry per survey response row,
        each containing the NPS event (score/label/value) plus the full
        account context (churn, opportunities, cases, gong) for that row's
        account — shape mirrors Agent 1+2's spec docs.

Sources:
    - Survey / NPS       : BigQuery churnzero_survey_response_data,
                            churnzero_survey_data (joined on SURVEY_ID)
    - Account / churn    : BigQuery churnzero_account_data (joined on
                            survey_response.ACCOUNT_ID -> account.ID, whose
                            CRM_ID is the real Salesforce account_id used
                            everywhere below)
    - Opportunities      : Salesforce MCP server, get_opportunities_by_account
                            (NOT the BigQuery opportunity_data table — per
                            requirement, opportunities come from Salesforce
                            live via MCP)
    - Cases              : Salesforce MCP server, get_cases_by_account
                            (Salesforce custom object CASE__c — NOT the
                            BigQuery case_data table)
    - Gong                : BigQuery gong_call_data_nps

MCP calling convention (identity-token auth, SSE session-per-call) copied
directly from scripts/data_collection_custom_agent/agent.py — same Cloud
Run service, same server.py, same auth requirements.
"""

import asyncio
import json
import os
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit

from google.adk.agents import BaseAgent
from google.adk.events import Event, EventActions
from google.adk.runners import InMemoryRunner
from google.auth.transport import requests as google_auth_requests
from google.cloud import bigquery
from google.oauth2 import id_token
from mcp import ClientSession
from mcp.client.sse import sse_client

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
GCP_PROJECT_ID = "atgeir-moae-dev"
DATASET_ID     = "nps"

TABLE_SURVEY_RESPONSE = f"{GCP_PROJECT_ID}.{DATASET_ID}.churnzero_survey_response_data"
TABLE_SURVEY          = f"{GCP_PROJECT_ID}.{DATASET_ID}.churnzero_survey_data"
TABLE_ACCOUNT         = f"{GCP_PROJECT_ID}.{DATASET_ID}.Churnzero_account_data_v2"
TABLE_GONG            = f"{GCP_PROJECT_ID}.{DATASET_ID}.gong_call_data_nps_v2"
TABLE_OPPORTUNITY = f"{GCP_PROJECT_ID}.{DATASET_ID}.opportunity_data"
# Salesforce Opportunities come from the custom Salesforce MCP server
# (salesforce_mcp_server/server.py), deployed as a Cloud Run endpoint,
# reached over SSE — NOT from BigQuery's opportunity_data table, per
# requirement. Same server/URL as the sales-conversion pipeline.
MCP_SALESFORCE_SERVER_URL = os.environ.get("MCP_SALESFORCE_SERVER_URL", "https://your-cloud-run-service-url/sse")

# Cloud Run's IAM proxy validates an identity token's `aud` claim against
# the service's base URL only (scheme + host) — see data_collection_custom_agent
# for the confirmed 403-without-this gotcha. Same fix applied here.
_mcp_url_parts = urlsplit(MCP_SALESFORCE_SERVER_URL)
MCP_SALESFORCE_SERVER_BASE_URL = f"{_mcp_url_parts.scheme}://{_mcp_url_parts.netloc}"

# Gong recency window for the account-context "recent_calls_count" /
# "recent_sentiment" summary — default 90 days, adjust if a different
# window is confirmed.
GONG_LOOKBACK_DAYS = 90

# How many most-recent open cases to carry into the account context payload.
MAX_OPEN_CASES_PER_ACCOUNT = 20

# Cap simultaneous MCP calls — firing one connection per account with no
# limit overwhelms the local server / Salesforce API when the batch has
# many distinct accounts (confirmed: 100+ concurrent calls caused an
# empty-message tool failure, likely a dropped connection under load).
MCP_CONCURRENCY_LIMIT = 1
_mcp_semaphore = asyncio.Semaphore(MCP_CONCURRENCY_LIMIT)


# ─────────────────────────────────────────────
# 0) MCP CLIENT — calls to the custom Salesforce MCP server
#    (identical pattern to data_collection_custom_agent/agent.py)
# ─────────────────────────────────────────────

async def _get_gcp_identity_token(audience: str) -> str:
    """
    Fetch a GCP identity token scoped to our own Cloud Run service's URL,
    using this pipeline's Application Default Credentials — required
    because salesforce_mcp_server is deployed with --no-allow-unauthenticated.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, id_token.fetch_id_token, google_auth_requests.Request(), audience
    )

async def _call_mcp_tool(tool_name: str, arguments: dict) -> dict:
    """
    Opens an SSE session to the Salesforce MCP server, calls one tool, and
    returns its parsed JSON result. A fresh session per call (not held open
    across the whole agent run) — simple, no shared connection lifecycle to
    manage across the parallel asyncio.gather() calls below.
    """
    identity_token = await _get_gcp_identity_token(MCP_SALESFORCE_SERVER_BASE_URL)
    async with sse_client(MCP_SALESFORCE_SERVER_URL, headers={"Authorization": f"Bearer {identity_token}"}) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            if result.isError:
                raise RuntimeError(f"MCP tool '{tool_name}' returned an error: {result.content}")
            return json.loads(result.content[0].text)


async def _fetch_opportunities_mcp(account_id: str) -> list[dict]:
    """
    Every opportunity on this Salesforce account, regardless of owner or
    open/closed status — via the MCP get_opportunities_by_account tool.
    Returns already-parsed records in soql.FIELD_MAP's clean field-name
    shape (opportunity_name, current_stage, next_step, opportunity_type,
    deal_value_arr, risks, cbi_raw_text, opportunity_manager_notes, etc.)
    """
    if not account_id:
        return []
    async with _mcp_semaphore:
        mcp_result = await _call_mcp_tool("get_opportunities_by_account", {"account_id": account_id})
    return mcp_result.get("opportunities", [])


async def _fetch_cases_mcp(account_id: str) -> list[dict]:
    """Every Case on this Salesforce account, via the MCP get_cases_by_account
    tool. Returns records in soql.CASE_FIELD_MAP's clean field-name shape."""
    if not account_id:
        return []
    async with _mcp_semaphore:
        mcp_result = await _call_mcp_tool("get_cases_by_account", {"account_id": account_id})
    return mcp_result.get("cases", [])

# ─────────────────────────────────────────────
# 1) SURVEY / NPS — BigQuery churnzero_survey_response_data + churnzero_survey_data
# ─────────────────────────────────────────────

def _fetch_survey_responses_sync() -> list[dict]:
    """
    BATCH MODE — pulls the whole table, every run, no filter.
    Joined to churnzero_survey_data on SURVEY_ID to resolve survey type
    (IS_ACTIVE -> "ongoing" vs not, per requirement doc).

    NOTE: when a real trigger/input is defined (single account_id, a
    date-range watermark, etc.), add the filter here — everything
    downstream keys off the rows this returns and needs no other change.
    """
    client = bigquery.Client(project=GCP_PROJECT_ID)
    query = f"""
        SELECT
            r.ID              AS response_id,
            r.ACCOUNT_ID      AS churnzero_account_id,
            r.CONTACT_ID      AS contact_id,
            r.SURVEY_ID       AS survey_id,
            r.DATE            AS survey_response_date,
            r.SCORE           AS survey_score,
            r.SOURCE          AS source,
            r.COMMENT         AS comment,
            s.IS_ACTIVE       AS survey_is_active,
            s.NAME            AS survey_name,
            s.TYPE            AS survey_definition_type,
            s.QUESTION                AS question,
            s.CAMPAIGN_STATUS         AS campaign_status,
            s.RECURRING_EVERY_MONTH   AS recurring_every_month,
            s.CAMPAIGN_TYPE           AS campaign_type,
            r.FOLLOW_UP_RESPONSE      AS follow_up_response,
            r.FOLLOW_UP_QUESTION      AS follow_up_question,
        FROM `{TABLE_SURVEY_RESPONSE}` r
        LEFT JOIN `{TABLE_SURVEY}` s
            ON r.SURVEY_ID = s.ID
        WHERE r._FIVETRAN_DELETED IS NOT TRUE
        ORDER BY r.DATE DESC
        LIMIT 10
    """
    rows = [dict(row) for row in client.query(query).result()]
    return rows


# ─────────────────────────────────────────────
# 2) ACCOUNT / CHURN — BigQuery churnzero_account_data
# ─────────────────────────────────────────────

def _fetch_accounts_by_id_sync(churnzero_account_ids: list[int]) -> dict[int, dict]:
    """
    Batched single lookup (not one query per row) — keyed by
    churnzero_account_data.ID so callers can join back to each survey
    response's ACCOUNT_ID. CRM_ID on each row is the real Salesforce
    account_id used for MCP (Opportunities, Cases) and gong_call_data_nps
    lookups.
    """
    if not churnzero_account_ids:
        return {}
    client = bigquery.Client(project=GCP_PROJECT_ID)
    query = f"""
        SELECT
            ID,
            NAME,
            CRM_ID,
            IS_ACTIVE,
            TENURE_IN_DAYS,
            PRIMARY_CHURN_SCORE_VALUE,
            NEXT_RENEWAL_DATE,
            TOTAL_CONTRACT_AMOUNT,
            USAGE_FREQUENCY,
        FROM `{TABLE_ACCOUNT}`
        WHERE ID IN UNNEST(@account_ids)
          AND _FIVETRAN_DELETED IS NOT TRUE
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ArrayQueryParameter("account_ids", "INT64", churnzero_account_ids)]
    )
    rows = [dict(row) for row in client.query(query, job_config=job_config).result()]
    return {row["ID"]: row for row in rows}


# ─────────────────────────────────────────────
# 4) GONG — BigQuery gong_call_data_nps
# ─────────────────────────────────────────────

def _fetch_gong_by_account_ids_sync(crm_account_ids: list[str]) -> dict[str, list[dict]]:
    """
    Batched single lookup, restricted to calls scheduled within the last
    GONG_LOOKBACK_DAYS days, grouped back by Salesforce Account ID.
    """
    if not crm_account_ids:
        return {}
    client = bigquery.Client(project=GCP_PROJECT_ID)
    query = f"""
        SELECT
            ACCOUNT_ID,
            OPPORTUNITY_ID,
            TITLE,
            STARTED,
            CUSTOMER_SENTIMENT,
            CALL_OUTCOME_NAME,
            PRIMARY_OBJECTION,
            NEXT_STEP,
            KEY_MEETING_DISCUSSIONS,
            CUSTOM_DATA,
            BRIEF,
            CALL_OUTCOME_CATEGORY,
            SALES_REP_ID,
            SALES_REP_NAME,
            SALES_REP_EMAIL,
            SALES_MANAGER_NAME,
            SALES_MANAGER_EMAIL,
        FROM `{TABLE_GONG}`
        WHERE ACCOUNT_ID IN UNNEST(@account_ids)
          AND STARTED >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @lookback_days DAY)
        ORDER BY STARTED DESC
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("account_ids", "STRING", crm_account_ids),
            bigquery.ScalarQueryParameter("lookback_days", "INT64", GONG_LOOKBACK_DAYS),
        ]
    )
    rows = [dict(row) for row in client.query(query, job_config=job_config).result()]

    calls_by_account: dict[str, list[dict]] = {}
    for row in rows:
        calls_by_account.setdefault(row["ACCOUNT_ID"], []).append(row)
    return calls_by_account

def _fetch_rep_manager_fallback_sync(account_names: list[str]) -> dict[str, dict]:
    """Fallback rep NAME source when Gong has zero calls for an account."""
    if not account_names:
        return {}
    client = bigquery.Client(project=GCP_PROJECT_ID)
    query = f"""
        SELECT
            `Account Name`   AS account_name,
            `Sales Rep Name` AS sales_rep_name
        FROM `{TABLE_OPPORTUNITY}`
        WHERE `Account Name` IN UNNEST(@account_names)
        ORDER BY `Opportunity Created Date` DESC
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ArrayQueryParameter("account_names", "STRING", account_names)]
    )
    rows = [dict(row) for row in client.query(query, job_config=job_config).result()]
    result = {}
    for row in rows:
        name = row["account_name"]
        if name not in result:
            result[name] = row
    return result


def _fetch_rep_directory_by_name_sync(rep_names: list[str]) -> dict[str, dict]:
    """Rep directory built from ALL Gong calls, keyed by rep NAME —
    finds a rep's email even when THIS account has zero calls."""
    if not rep_names:
        return {}
    client = bigquery.Client(project=GCP_PROJECT_ID)
    query = f"""
        SELECT DISTINCT
            SALES_REP_ID,
            SALES_REP_NAME,
            SALES_REP_EMAIL,
            SALES_MANAGER_NAME,
            SALES_MANAGER_EMAIL
        FROM `{TABLE_GONG}`
        WHERE SALES_REP_NAME IN UNNEST(@rep_names)
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ArrayQueryParameter("rep_names", "STRING", rep_names)]
    )
    rows = [dict(row) for row in client.query(query, job_config=job_config).result()]
    return {row["SALES_REP_NAME"]: row for row in rows if row.get("SALES_REP_NAME")}


# ─────────────────────────────────────────────
# ASYNC WRAPPER
# ─────────────────────────────────────────────

async def _run(fn, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fn, *args)


# ─────────────────────────────────────────────
# DERIVED METRICS / JSON ASSEMBLY
# ─────────────────────────────────────────────

def label_for_score(score: int | None) -> str | None:
    if score is None:
        return None
    if score >= 9:
        return "Promoter"
    if score >= 7:
        return "Passive"
    return "Detractor"


def build_nps_summary(all_scores: list[int]) -> dict:
    """
    NPS = %Promoters - %Detractors (Passives excluded from the calculation,
    included only in the denominator for percentage math) — per the
    requirement doc's formula and worked example.
    """
    total = len(all_scores)
    if total == 0:
        return {"promoter_pct": None, "passive_pct": None, "detractor_pct": None, "nps_value": None}

    promoters = sum(1 for s in all_scores if s >= 9)
    passives = sum(1 for s in all_scores if 7 <= s <= 8)
    detractors = sum(1 for s in all_scores if s <= 6)

    promoter_pct = round(promoters / total * 100, 1)
    passive_pct = round(passives / total * 100, 1)
    detractor_pct = round(detractors / total * 100, 1)
    nps_value = round(promoter_pct - detractor_pct, 1)

    return {
        "promoter_pct": promoter_pct,
        "passive_pct": passive_pct,
        "detractor_pct": detractor_pct,
        "nps_value": nps_value,
    }


def build_gong_summary(calls: list[dict]) -> dict:
    if not calls:
        return {
            "recent_calls_count": 0,
            "recent_sentiment": None,
            "sales_rep": {"id": None, "name": None, "email": None},
            "sales_manager": {"name": None, "email": None},
        }

    sentiments = [c["CUSTOMER_SENTIMENT"] for c in calls if c.get("CUSTOMER_SENTIMENT")]
    if not sentiments:
        recent_sentiment = None
    elif len(set(sentiments)) == 1:
        recent_sentiment = sentiments[0]
    else:
        recent_sentiment = "mixed"

    latest_call = calls[0]  # calls are ORDER BY STARTED DESC

    return {
        "recent_calls_count": len(calls),
        "recent_sentiment": recent_sentiment,
        "sales_rep": {
            "id": latest_call.get("SALES_REP_ID"),
            "name": latest_call.get("SALES_REP_NAME"),
            "email": latest_call.get("SALES_REP_EMAIL"),
        },
        "sales_manager": {
            "name": latest_call.get("SALES_MANAGER_NAME"),
            "email": latest_call.get("SALES_MANAGER_EMAIL"),
        },
        "recent_calls": calls  # This injects all the new Gong fields directly
    }


def build_case_summary(cases: list[dict]) -> dict:
    open_cases = [c for c in cases if not c.get("is_closed")]
    has_open_high_priority = any(c.get("priority") == "High" for c in open_cases)
    latest_case_reason = cases[0].get("reason") if cases else None  # cases pre-sorted DESC by Created Date

    return {
        "open_cases": [
            {
                "case_id": c.get("case_id"),
                "status": c.get("status"),
                "reason": c.get("reason"),
                "subject": c.get("subject"),
                "priority": c.get("priority"),
                "severity": c.get("severity"),
                "is_closed": c.get("is_closed"),
                "is_escalated": c.get("is_escalated"),
                "root_cause": c.get("root_cause"),
                "customer_sentiment": c.get("customer_sentiment"),
                "nps_risk_level": c.get("nps_risk_level"),
                "nps_risk_reason": c.get("nps_risk_reason"),
                "recommended_agent_action": c.get("recommended_agent_action"),
                "date_time": c.get("created_date"),
                "case_number": c.get("case_number"),
                "case_type": c.get("case_type"),
                "product_area": c.get("product_area"),
                "description": c.get("description"),
                "first_response_date": c.get("first_response_date"),
                "last_interaction_date": c.get("last_interaction_date"),
                "closed_date": c.get("closed_date"),
                "sla_status": c.get("sla_status"),
                "escalation_level": c.get("escalation_level"),
                "comment_count": c.get("comment_count"),
                "latest_customer_comment": c.get("latest_customer_comment"),
                "latest_internal_note": c.get("latest_internal_note"),
                "resolution_category": c.get("resolution_category"),
                "resolution_summary": c.get("resolution_summary"),
                "customer_health": c.get("customer_health"),
                "customer_success_manager": c.get("customer_success_manager"),
                "case_owner": c.get("case_owner"),
                "sales_rep_name": c.get("sales_rep_name"),
            }
            for c in open_cases[:MAX_OPEN_CASES_PER_ACCOUNT]
        ],
        "has_open_high_priority": has_open_high_priority,
        "latest_case_reason": latest_case_reason,
    }


def build_opportunity_summary(opportunities: list[dict]) -> dict:
    closed_won = [o for o in opportunities if o.get("is_won")]
    latest_closed_won_date = max(
        (o.get("close_date_target") for o in closed_won if o.get("close_date_target")),
        default=None,
    )
    open_opps = [o for o in opportunities if not o.get("is_closed")]

    return {
        "latest_closed_won_date": latest_closed_won_date,
        "open_opportunities": [
            {
                "opportunity_id": o.get("opportunity_id"),
                "name": o.get("opportunity_name"),
                "stage_name": o.get("current_stage"),
                "next_step": o.get("next_step"),
                "type": o.get("opportunity_type"),
                "deal_value_arr": o.get("deal_value_arr"),
                "risks": o.get("risks"),
                "cbi_raw_text": o.get("cbi_raw_text"),
                "opportunity_manager_notes": o.get("opportunity_manager_notes"),
                "deal_size": o.get("deal_value_arr"), 
                "closed_date": o.get("close_date_target"),
                "created_date": o.get("created_date"),
                "solutions_engineer_notes": o.get("solutions_engineer_notes"),
                "competitor": o.get("competitor"),
                "win_loss_reason": o.get("win_loss_reason"),
                "win_loss_reason_details": o.get("win_loss_reason_details"),
                "sales_rep_name": o.get("sales_rep_name"),
                "sales_manager": o.get("sales_manager"),
                "sales_vp_name": o.get("sales_vp_name"),
                "account_type": o.get("account_type"),
                "account_segment": o.get("account_segment"),
                "account_geo": o.get("account_geo"),
                "account_region": o.get("account_region"),
                "account_subregion": o.get("account_subregion"),
                "account_country": o.get("account_country"),
                "account_industry": o.get("industry"),
                "bdr": o.get("bdr"),
            }
            for o in open_opps
        ],
    }


def build_account_context(
    survey_row: dict,
    account_row: dict | None,
    opportunities: list[dict],
    cases: list[dict],
    gong_calls: list[dict],
    rep_manager_fallback: dict,
    rep_directory: dict,
) -> dict:
    score = survey_row.get("survey_score")
    survey_type = "ongoing" if survey_row.get("survey_is_active") else "one-time"

    gong_summary = build_gong_summary(gong_calls)
    rep_id = gong_summary["sales_rep"]["id"]
    rep_name = gong_summary["sales_rep"]["name"]
    rep_email = gong_summary["sales_rep"]["email"]
    manager_name = gong_summary["sales_manager"]["name"]
    manager_email = gong_summary["sales_manager"]["email"]

    if not rep_name and account_row:
        fallback = rep_manager_fallback.get(account_row.get("NAME"), {})
        rep_name = fallback.get("sales_rep_name")
        if rep_name:
            directory_entry = rep_directory.get(rep_name, {})
            rep_id = directory_entry.get("SALES_REP_ID")
            rep_email = directory_entry.get("SALES_REP_EMAIL")
            manager_name = directory_entry.get("SALES_MANAGER_NAME")
            manager_email = directory_entry.get("SALES_MANAGER_EMAIL")

    return {
        "account_id": account_row.get("CRM_ID") if account_row else None,
        "account_name": account_row.get("NAME") if account_row else None,
        "rep_id": rep_id,
        "rep_name": rep_name,
        "rep_email": rep_email,
        "manager_name": manager_name,
        "manager_email": manager_email,
        "survey": {
            "response_id": survey_row.get("response_id"),
            "survey_id": survey_row.get("survey_id"),
            "name": survey_row.get("survey_name"),
            "type": survey_type,
            "campaign_type": survey_row.get("campaign_type"),
            "campaign_status": survey_row.get("campaign_status"),
            "question": survey_row.get("question"),
            "recurring_every_month": survey_row.get("recurring_every_month"),
            "score": score,
            "label": label_for_score(score),
            "date": survey_row["survey_response_date"].isoformat() if survey_row.get("survey_response_date") else None,
            "comment": survey_row.get("comment"),
            "follow_up_question": survey_row.get("follow_up_question"),
            "follow_up_response": survey_row.get("follow_up_response"),
        },
        "churn": {
            "account_name": account_row.get("NAME") if account_row else None,
            "is_active": account_row.get("IS_ACTIVE") if account_row else None,
            "is_churn_account": (account_row.get("IS_ACTIVE") is False) if account_row else None,
            "tenure_in_days": account_row.get("TENURE_IN_DAYS") if account_row else None,
            "total_contract_amount": account_row.get("TOTAL_CONTRACT_AMOUNT") if account_row else None,
            "primary_churn_score_value": account_row.get("PRIMARY_CHURN_SCORE_VALUE") if account_row else None,
            "usage_frequency": account_row.get("USAGE_FREQUENCY") if account_row else None,
            "next_renewal_date": (
                account_row["NEXT_RENEWAL_DATE"].isoformat()
                if account_row and account_row.get("NEXT_RENEWAL_DATE") else None
            ),
        },
        "opportunities": build_opportunity_summary(opportunities),
        "cases": build_case_summary(cases),
        "gong": gong_summary,
    }
    


# ─────────────────────────────────────────────
# CUSTOM ADK AGENT
# ─────────────────────────────────────────────

class NpsAccountContextAgent(BaseAgent):
    """
    Merged Agent 1 (Survey Ingestion & NPS Label) + Agent 2 (Account
    Context Aggregation) — custom non-LLM data collection agent.

    Input  (session state): none required — BATCH MODE, pulls the whole
        churnzero_survey_response_data table every run. Swap the filter in
        _fetch_survey_responses_sync once a real per-run input is defined.

    Output (session state):
        nps_account_contexts → list[dict], one per survey response row,
            each with the NPS event + full account context. Also writes
            nps_summary → account-level aggregate NPS (%Promoters,
            %Passives, %Detractors, NPS value) across the whole batch.
    """

    async def _run_async_impl(self, ctx):
        print("\n[NpsAccountContextAgent] Starting batch run (no input filter)")

        # Step 1: pull the whole survey response batch (BigQuery, sync -> _run)
        survey_rows = await _run(_fetch_survey_responses_sync)
        print(f"[NpsAccountContextAgent] Fetched {len(survey_rows)} survey response row(s)")
        seen_accounts = set()
        deduped_rows = []
        for row in survey_rows:
            acct_id = row.get("churnzero_account_id")
            if acct_id not in seen_accounts:
                seen_accounts.add(acct_id)
                deduped_rows.append(row)
        survey_rows = deduped_rows
        print(f"[NpsAccountContextAgent] Deduped to {len(survey_rows)} unique account(s)")

        if not survey_rows:
            empty_payload = {
                "summary": build_nps_summary([]),
                "account_contexts": []
            }
            yield Event(
                author=self.name,
                content=None,
                actions=EventActions(state_delta={"nps_payload": empty_payload}),
            )
            return

        # Step 2: resolve churnzero_account_data for every distinct
        # ACCOUNT_ID in this batch, in one batched query (not N queries).
        churnzero_account_ids = sorted({
            r["churnzero_account_id"] for r in survey_rows if r.get("churnzero_account_id") is not None
        })
        accounts_by_id = await _run(_fetch_accounts_by_id_sync, churnzero_account_ids)

        # Step 3: resolve the real Salesforce account_id (CRM_ID) per row,
        # then batch-fetch Cases + Gong (BigQuery) for every distinct CRM_ID
        # up front — same batched-not-per-row approach.
        crm_ids_by_response: dict[int, str | None] = {}
        for row in survey_rows:
            account_row = accounts_by_id.get(row.get("churnzero_account_id"))
            crm_ids_by_response[row["response_id"]] = account_row.get("CRM_ID") if account_row else None

        distinct_crm_ids = sorted({v for v in crm_ids_by_response.values() if v})

        gong_by_account = await _run(_fetch_gong_by_account_ids_sync, distinct_crm_ids)

        # Step 3b: fallback rep/manager sources for accounts with zero Gong calls
        account_names = [a.get("NAME") for a in accounts_by_id.values() if a.get("NAME")]
        rep_manager_fallback = await _run(_fetch_rep_manager_fallback_sync, account_names)

        rep_names_needing_email = list({
            v.get("sales_rep_name") for v in rep_manager_fallback.values() if v.get("sales_rep_name")
        })
        rep_directory = await _run(_fetch_rep_directory_by_name_sync, rep_names_needing_email)

        # Step 4: fetch Opportunities per distinct account via Salesforce
        # MCP, in parallel across accounts (native async, no _run wrapping).
        opp_results, case_results = await asyncio.gather(
            asyncio.gather(*[_fetch_opportunities_mcp(crm_id) for crm_id in distinct_crm_ids]),
            asyncio.gather(*[_fetch_cases_mcp(crm_id) for crm_id in distinct_crm_ids]),
        )
        opportunities_by_account = dict(zip(distinct_crm_ids, opp_results))
        cases_by_account = dict(zip(distinct_crm_ids, case_results))

        print(f"[NpsAccountContextAgent] Resolved {len(distinct_crm_ids)} distinct Salesforce account(s) → "
              f"opportunities/cases/gong fetched")

        # Step 5: assemble one account-context object per survey response row.
        nps_account_contexts = []
        for row in survey_rows:
            crm_id = crm_ids_by_response.get(row["response_id"])
            account_row = accounts_by_id.get(row.get("churnzero_account_id"))
            context = build_account_context(
                survey_row=row,
                account_row=account_row,
                opportunities=opportunities_by_account.get(crm_id, []),
                cases=cases_by_account.get(crm_id, []),
                gong_calls=gong_by_account.get(crm_id, []),
                rep_manager_fallback=rep_manager_fallback,
                rep_directory=rep_directory,
            )
            nps_account_contexts.append(context)

        # Step 6: batch-level NPS summary (%Promoters/%Passives/%Detractors, NPS value)
        all_scores = [r["survey_score"] for r in survey_rows if r.get("survey_score") is not None]
        nps_summary = build_nps_summary(all_scores)

        # Step 7: build payload and commit via state_delta — the ADK
        # mechanism that actually persists state across sub-agents in a
        # SequentialAgent. Direct ctx.session.state[...] = ... mutation
        # is not reliably committed to the session snapshot that
        # downstream agents / api.py read.
        nps_payload = {
            "summary": nps_summary,
            "account_contexts": nps_account_contexts
        }

        print("\n── Final session state: nps_payload (Summary) ──")
        print(json.dumps(nps_summary, indent=2, default=str))

        print(f"\n── nps_payload (Account Contexts: {len(nps_account_contexts)} entries) ──")
        print(json.dumps(nps_account_contexts, indent=2, default=str))

        yield Event(
            author=self.name,
            content=None,
            actions=EventActions(state_delta={"nps_payload": nps_payload}),
        )


nps_data_collection_agent = NpsAccountContextAgent(name="nps_data_collection_agent")


# ─────────────────────────────────────────────
# LOCAL TEST
# ─────────────────────────────────────────────

async def test():
    from google.genai import types

    global _get_gcp_identity_token
    async def _dummy_identity_token(audience: str) -> str:
        return "local-dev-dummy-token"
    _get_gcp_identity_token = _dummy_identity_token

    runner = InMemoryRunner(
        agent=NpsAccountContextAgent(name="NpsAccountContextAgent"),
        app_name="nps_pipeline",
    )

    session_service = runner.session_service

    session = await session_service.create_session(
        app_name="nps_pipeline",
        user_id="test_user",
        state={},  # batch mode — no input needed yet
    )

    async for event in runner.run_async(
        user_id="test_user",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text="start")]),
    ):
        print("\nEvent received from:", event.author)

    final = await session_service.get_session(
        app_name="nps_pipeline", user_id="test_user", session_id=session.id,
    )
    
    # Extract the combined object from the final session state
    payload = final.state.get("nps_payload", {})
    
    print("\n── Final session state: nps_payload (Summary) ──")
    print(json.dumps(payload.get("summary"), indent=2, default=str))
    
    contexts = payload.get("account_contexts", [])
    print(f"\n── nps_payload (Account Contexts: {len(contexts)} entries) ──")
    print(json.dumps(contexts, indent=2, default=str))

if __name__ == "__main__":
    asyncio.run(test())