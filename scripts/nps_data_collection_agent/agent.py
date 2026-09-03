"""
scripts/nps_account_context_agent/agent.py

AZURE VERSION — Agent 1 (Survey Ingestion & NPS Label + Account Context
Aggregation), rewritten for Azure SQL Database + Microsoft Agent Framework.

WHAT CHANGED FROM THE GCP/ADK VERSION (see inline # === AZURE CHANGE === markers):
  1. Imports        : google.cloud.bigquery -> pyodbc + azure.identity
  2. Config block    : GCP_PROJECT_ID/DATASET_ID -> SQL_SERVER/SQL_DATABASE
  3. New helper      : _get_sql_connection() replaces bigquery.Client(...)
  4. Query functions : BigQuery UNNEST(@param) -> T-SQL OPENJSON pattern;
                        LIMIT -> TOP; client.query().result() -> cursor.execute()
  5. Agent class     : ADK BaseAgent/Event/EventActions removed entirely —
                        replaced with a plain async function that Agent
                        Framework's workflow calls directly as a step,
                        writing output via ctx.set_shared_state(...)
  6. Local test      : ADK InMemoryRunner removed — just calls the function

WHAT DID NOT CHANGE (left exactly as before):
  - _get_gcp_identity_token(), _call_mcp_tool(), _fetch_opportunities_mcp(),
    _fetch_cases_mcp() — the Salesforce MCP integration. This still uses
    GCP identity-token auth because the MCP server's hosting location
    (GCP vs Azure) has not been confirmed yet by your colleague. If it
    moves to Azure, this section will need a matching auth swap
    (DefaultAzureCredential instead of id_token.fetch_id_token) — flagged
    clearly below so it's easy to find later.
  - Every build_*() function (build_nps_summary, build_gong_summary,
    build_case_summary, build_opportunity_summary, build_account_context)
    — pure Python, no cloud dependency, zero changes.
  - _run() async executor wrapper — works identically with pyodbc.
"""

import asyncio
import json
import struct                                            # === AZURE CHANGE === needed to pack the Managed Identity token for pyodbc
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit
from agent_framework import Executor, WorkflowContext, WorkflowBuilder, executor

import pyodbc                                             # === AZURE CHANGE === replaces google.cloud.bigquery
from azure.identity import DefaultAzureCredential         # === AZURE CHANGE === replaces google.oauth2.id_token (for SQL auth only)

# --- UNCHANGED: Salesforce MCP client still uses GCP identity-token auth ---
# --- until MCP server hosting location is confirmed. See module docstring. ---
from google.auth.transport import requests as google_auth_requests
from google.oauth2 import id_token
from mcp import ClientSession
from mcp.client.sse import sse_client


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

# === AZURE CHANGE === GCP_PROJECT_ID / DATASET_ID replaced with Azure SQL
# server + database. Get SQL_SERVER from the Azure Portal: your SQL
# Database resource -> Overview -> "Server name" field.
SQL_SERVER = "atg-agents-server.database.windows.net"
SQL_DATABASE = "atg-agents-db"
SQL_SCHEMA = "nps"

# === AZURE CHANGE === table refs no longer need a project/dataset prefix —
# the database is implicit once connected, so only schema.table remains.
TABLE_SURVEY_RESPONSE = f"{SQL_SCHEMA}.churnzero_survey_response_data"
TABLE_SURVEY          = f"{SQL_SCHEMA}.churnzero_survey_data"
TABLE_ACCOUNT         = f"{SQL_SCHEMA}.Churnzero_account_data_v2"
TABLE_GONG            = f"{SQL_SCHEMA}.gong_call_data_nps_v2"
TABLE_OPPORTUNITY     = f"{SQL_SCHEMA}.opportunity_data"

# === AZURE CHANGE === scope used to request a Managed Identity token for
# Azure SQL specifically — this exact string is fixed by Azure, not a
# value you choose.
AZURE_SQL_TOKEN_SCOPE = "https://database.windows.net/.default"

# --- UNCHANGED: Salesforce MCP server config ---
import os
MCP_SALESFORCE_SERVER_URL = os.environ.get("MCP_SALESFORCE_SERVER_URL", "https://your-cloud-run-service-url/sse")
_mcp_url_parts = urlsplit(MCP_SALESFORCE_SERVER_URL)
MCP_SALESFORCE_SERVER_BASE_URL = f"{_mcp_url_parts.scheme}://{_mcp_url_parts.netloc}"

GONG_LOOKBACK_DAYS = 90
MAX_OPEN_CASES_PER_ACCOUNT = 20
MCP_CONCURRENCY_LIMIT = 1
_mcp_semaphore = asyncio.Semaphore(MCP_CONCURRENCY_LIMIT)


# ─────────────────────────────────────────────
# === AZURE CHANGE === NEW — Azure SQL connection helper
# Replaces bigquery.Client(project=GCP_PROJECT_ID). Uses Managed Identity
# (no username/password anywhere in code) via DefaultAzureCredential.
# ─────────────────────────────────────────────

def _get_sql_connection() -> pyodbc.Connection:
    """
    Opens an authenticated connection to Azure SQL using a Managed
    Identity token. Call this once per _fetch_*_sync function, same as
    the old `bigquery.Client(project=GCP_PROJECT_ID)` line.
    """
    credential = DefaultAzureCredential()
    token = credential.get_token(AZURE_SQL_TOKEN_SCOPE)

    token_bytes = token.token.encode("utf-16-le")
    token_struct = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)

    conn_str = (
        f"Driver={{ODBC Driver 18 for SQL Server}};"
        f"Server=tcp:{SQL_SERVER},1433;"
        f"Database={SQL_DATABASE};"
        f"Encrypt=yes;TrustServerCertificate=no;"
    )
    # SQL_COPT_SS_ACCESS_TOKEN = 1256 — the ODBC attribute that carries a
    # Managed Identity token instead of a username/password.
    return pyodbc.connect(conn_str, attrs_before={1256: token_struct})


def _rows_to_dicts(cursor: pyodbc.Cursor) -> list[dict]:
    """
    === AZURE CHANGE === NEW helper.
    pyodbc cursors return plain tuples, unlike BigQuery's client which
    returns mapping-like rows that dict(row) converts directly. This
    rebuilds the same list[dict] shape every build_*() function expects.
    """
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


# ─────────────────────────────────────────────
# 0) MCP CLIENT — calls to the custom Salesforce MCP server
#    UNCHANGED — still GCP identity-token auth. See module docstring.
# ─────────────────────────────────────────────

async def _get_gcp_identity_token(audience: str) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, id_token.fetch_id_token, google_auth_requests.Request(), audience
    )


async def _call_mcp_tool(tool_name: str, arguments: dict) -> dict:
    # TEMP: no auth — salesforce-mcp-server has no identity provider configured
    # yet on Container Apps (Easy Auth not set up). Circle back and restore
    # a proper Authorization header once that's locked down.
    async with sse_client(MCP_SALESFORCE_SERVER_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            if result.is_error:
                raise RuntimeError(f"MCP tool '{tool_name}' returned an error: {result.content}")
            return json.loads(result.content[0].text)


async def _fetch_opportunities_mcp(account_id: str) -> list[dict]:
    if not account_id:
        return []
    async with _mcp_semaphore:
        mcp_result = await _call_mcp_tool("get_opportunities_by_account", {"account_id": account_id})
    return mcp_result.get("opportunities", [])


async def _fetch_cases_mcp(account_id: str) -> list[dict]:
    if not account_id:
        return []
    async with _mcp_semaphore:
        mcp_result = await _call_mcp_tool("get_cases_by_account", {"account_id": account_id})
    return mcp_result.get("cases", [])


# ─────────────────────────────────────────────
# 1) SURVEY / NPS — Azure SQL churnzero_survey_response_data + churnzero_survey_data
# === AZURE CHANGE === BigQuery client -> pyodbc; LIMIT -> TOP
# ─────────────────────────────────────────────

def _fetch_survey_responses_sync() -> list[dict]:
    conn = _get_sql_connection()
    try:
        cursor = conn.cursor()
        query = f"""
            SELECT TOP 10
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
                r.FOLLOW_UP_QUESTION      AS follow_up_question
            FROM {TABLE_SURVEY_RESPONSE} r
            LEFT JOIN {TABLE_SURVEY} s
                ON r.SURVEY_ID = s.ID
            WHERE r._FIVETRAN_DELETED = 0
            ORDER BY r.DATE DESC
        """
        cursor.execute(query)
        return _rows_to_dicts(cursor)
    finally:
        conn.close()


# ─────────────────────────────────────────────
# 2) ACCOUNT / CHURN — Azure SQL Churnzero_account_data_v2
# === AZURE CHANGE === UNNEST(@account_ids) -> OPENJSON(@account_ids_json)
# ─────────────────────────────────────────────

def _fetch_accounts_by_id_sync(churnzero_account_ids: list[int]) -> dict[int, dict]:
    if not churnzero_account_ids:
        return {}
    conn = _get_sql_connection()
    try:
        cursor = conn.cursor()
        query = f"""
            SELECT
                ID, NAME, CRM_ID, IS_ACTIVE, TENURE_IN_DAYS,
                PRIMARY_CHURN_SCORE_VALUE, NEXT_RENEWAL_DATE,
                TOTAL_CONTRACT_AMOUNT, USAGE_FREQUENCY
            FROM {TABLE_ACCOUNT}
            WHERE ID IN (SELECT value FROM OPENJSON(?))
              AND _FIVETRAN_DELETED = 0
        """
        cursor.execute(query, (json.dumps(churnzero_account_ids),))
        rows = _rows_to_dicts(cursor)
        return {row["ID"]: row for row in rows}
    finally:
        conn.close()


# ─────────────────────────────────────────────
# 4) GONG — Azure SQL gong_call_data_nps_v2
# === AZURE CHANGE === UNNEST(@account_ids) -> OPENJSON; TIMESTAMP_SUB -> DATEADD
# ─────────────────────────────────────────────

def _fetch_gong_by_account_ids_sync(crm_account_ids: list[str]) -> dict[str, list[dict]]:
    if not crm_account_ids:
        return {}
    conn = _get_sql_connection()
    try:
        cursor = conn.cursor()
        query = f"""
            SELECT
                ACCOUNT_ID, OPPORTUNITY_ID, TITLE, STARTED,
                CUSTOMER_SENTIMENT, CALL_OUTCOME_NAME, PRIMARY_OBJECTION,
                NEXT_STEP, KEY_MEETING_DISCUSSIONS, CUSTOM_DATA, BRIEF,
                CALL_OUTCOME_CATEGORY, SALES_REP_ID, SALES_REP_NAME,
                SALES_REP_EMAIL, SALES_MANAGER_NAME, SALES_MANAGER_EMAIL
            FROM {TABLE_GONG}
            WHERE ACCOUNT_ID IN (SELECT value FROM OPENJSON(?))
              AND STARTED >= DATEADD(DAY, -?, SYSUTCDATETIME())
            ORDER BY STARTED DESC
        """
        cursor.execute(query, (json.dumps(crm_account_ids), GONG_LOOKBACK_DAYS))
        rows = _rows_to_dicts(cursor)
    finally:
        conn.close()

    calls_by_account: dict[str, list[dict]] = {}
    for row in rows:
        calls_by_account.setdefault(row["ACCOUNT_ID"], []).append(row)
    return calls_by_account


def _fetch_rep_manager_fallback_sync(account_names: list[str]) -> dict[str, dict]:
    if not account_names:
        return {}
    conn = _get_sql_connection()
    try:
        cursor = conn.cursor()
        query = f"""
            SELECT
                [Account Name]   AS account_name,
                [Sales Rep Name] AS sales_rep_name
            FROM {TABLE_OPPORTUNITY}
            WHERE [Account Name] IN (SELECT value FROM OPENJSON(?))
            ORDER BY [Opportunity Created Date] DESC
        """
        cursor.execute(query, (json.dumps(account_names),))
        rows = _rows_to_dicts(cursor)
    finally:
        conn.close()

    result = {}
    for row in rows:
        name = row["account_name"]
        if name not in result:
            result[name] = row
    return result


def _fetch_rep_directory_by_name_sync(rep_names: list[str]) -> dict[str, dict]:
    if not rep_names:
        return {}
    conn = _get_sql_connection()
    try:
        cursor = conn.cursor()
        query = f"""
            SELECT DISTINCT
                SALES_REP_ID, SALES_REP_NAME, SALES_REP_EMAIL,
                SALES_MANAGER_NAME, SALES_MANAGER_EMAIL
            FROM {TABLE_GONG}
            WHERE SALES_REP_NAME IN (SELECT value FROM OPENJSON(?))
        """
        cursor.execute(query, (json.dumps(rep_names),))
        rows = _rows_to_dicts(cursor)
    finally:
        conn.close()

    return {row["SALES_REP_NAME"]: row for row in rows if row.get("SALES_REP_NAME")}


# ─────────────────────────────────────────────
# ASYNC WRAPPER — UNCHANGED, works identically with pyodbc
# ─────────────────────────────────────────────

async def _run(fn, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fn, *args)


# ─────────────────────────────────────────────
# DERIVED METRICS / JSON ASSEMBLY — UNCHANGED, pure Python
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

    latest_call = calls[0]

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
        "recent_calls": calls,
    }


def build_case_summary(cases: list[dict]) -> dict:
    open_cases = [c for c in cases if not c.get("is_closed")]
    has_open_high_priority = any(c.get("priority") == "High" for c in open_cases)
    latest_case_reason = cases[0].get("reason") if cases else None

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
# === AZURE CHANGE === REPLACES: class NpsAccountContextAgent(BaseAgent)
#
# ADK required this step to subclass BaseAgent and yield Event objects
# with EventActions(state_delta=...) purely to participate in the
# SequentialAgent pipeline. Since this step has no LLM call, Microsoft
# Agent Framework does not require it to look like an "Agent" at all —
# it becomes a plain async function that a workflow executor calls
# directly, writing its result via ctx.set_shared_state(...).
# ─────────────────────────────────────────────

@executor(id="nps_data_collection")
async def collect_nps_data(_: str, ctx: WorkflowContext[dict]) -> None:
    ...
    """
    Agent 1 replacement — plain async function, not an Agent subclass.

    `ctx` here is Agent Framework's WorkflowContext (passed in by whatever
    executor/workflow step calls this function) — NOT ADK's session
    context. Used only to write the shared-state output at the end.

    Returns nps_payload directly (for send_message-style chaining) AND
    writes it to shared state (for get_shared_state-style reads by
    downstream steps) — matching the "any step can read this" pattern
    your ADK session.state usage relied on.
    """
    print("\n[collect_nps_data] Starting batch run (no input filter)")

    survey_rows = await _run(_fetch_survey_responses_sync)
    print(f"[collect_nps_data] Fetched {len(survey_rows)} survey response row(s)")

    seen_accounts = set()
    deduped_rows = []
    for row in survey_rows:
        acct_id = row.get("churnzero_account_id")
        if acct_id not in seen_accounts:
            seen_accounts.add(acct_id)
            deduped_rows.append(row)
    survey_rows = deduped_rows
    print(f"[collect_nps_data] Deduped to {len(survey_rows)} unique account(s)")

    if not survey_rows:
        empty_payload = {"summary": build_nps_summary([]), "account_contexts": []}
        await ctx.set_shared_state("nps_payload", empty_payload)
        await ctx.send_message(empty_payload)
        return

    churnzero_account_ids = sorted({
        r["churnzero_account_id"] for r in survey_rows if r.get("churnzero_account_id") is not None
    })
    accounts_by_id = await _run(_fetch_accounts_by_id_sync, churnzero_account_ids)

    crm_ids_by_response: dict[int, str | None] = {}
    for row in survey_rows:
        account_row = accounts_by_id.get(row.get("churnzero_account_id"))
        crm_ids_by_response[row["response_id"]] = account_row.get("CRM_ID") if account_row else None

    distinct_crm_ids = sorted({v for v in crm_ids_by_response.values() if v})

    gong_by_account = await _run(_fetch_gong_by_account_ids_sync, distinct_crm_ids)

    account_names = [a.get("NAME") for a in accounts_by_id.values() if a.get("NAME")]
    rep_manager_fallback = await _run(_fetch_rep_manager_fallback_sync, account_names)

    rep_names_needing_email = list({
        v.get("sales_rep_name") for v in rep_manager_fallback.values() if v.get("sales_rep_name")
    })
    rep_directory = await _run(_fetch_rep_directory_by_name_sync, rep_names_needing_email)

    opp_results, case_results = await asyncio.gather(
        asyncio.gather(*[_fetch_opportunities_mcp(crm_id) for crm_id in distinct_crm_ids]),
        asyncio.gather(*[_fetch_cases_mcp(crm_id) for crm_id in distinct_crm_ids]),
    )
    opportunities_by_account = dict(zip(distinct_crm_ids, opp_results))
    cases_by_account = dict(zip(distinct_crm_ids, case_results))

    print(f"[collect_nps_data] Resolved {len(distinct_crm_ids)} distinct Salesforce account(s) → "
          f"opportunities/cases/gong fetched")

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

    all_scores = [r["survey_score"] for r in survey_rows if r.get("survey_score") is not None]
    nps_summary = build_nps_summary(all_scores)

    nps_payload = {
        "summary": nps_summary,
        "account_contexts": nps_account_contexts,
    }

    print("\n── nps_payload (Summary) ──")
    print(json.dumps(nps_summary, indent=2, default=str))
    print(f"\n── nps_payload (Account Contexts: {len(nps_account_contexts)} entries) ──")
    print(json.dumps(nps_account_contexts, indent=2, default=str))

    # === AZURE CHANGE === replaces: yield Event(..., EventActions(state_delta={"nps_payload": nps_payload}))
    await ctx.set_shared_state("nps_payload", nps_payload)
    await ctx.send_message(nps_payload)


# ─────────────────────────────────────────────
# LOCAL TEST
# === AZURE CHANGE === ADK InMemoryRunner removed — just calls the
# function directly with a minimal stand-in ctx object.
# ─────────────────────────────────────────────



async def test():
    workflow = (
        WorkflowBuilder()
        .set_start_executor(collect_nps_data)
        .build()
    )
    result = await workflow.run("start")
    print(result.get_outputs())

if __name__ == "__main__":
    asyncio.run(test())