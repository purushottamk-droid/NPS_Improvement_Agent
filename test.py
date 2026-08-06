"""
salesforce_mcp_server/server.py

Custom, self-hosted MCP server exposing exactly the two purpose-built
Salesforce tools this pipeline needs — see the plan doc ("Build a Custom
Salesforce MCP Server on GCP") for why this exists instead of using
Salesforce's own hosted MCP server (Identity Passthrough auth model
doesn't fit an unattended, org-wide backend service).

Deployed as its own Cloud Run service, separate from the main ADK
pipeline. Cloud Run IAM (--no-allow-unauthenticated) gates access — only
callable by authenticated GCP identities, not the public internet.
"""

import asyncio
import os
from datetime import date, timedelta

import httpx
from mcp.server.fastmcp import FastMCP

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # fine in production — Cloud Run injects real env vars directly, no .env file involved

from .salesforce_auth import get_salesforce_session
from .soql import (
    build_attainment_current_month_soql,
    build_attainment_trailing_3_months_soql,
    build_opportunities_by_account_soql,
    build_opportunities_by_rep_name_soql,
    build_stage_benchmark_soql,
    parse_opportunity_record,
)

SALESFORCE_API_VERSION = os.environ.get("SALESFORCE_API_VERSION", "v60.0")

mcp = FastMCP(
    "salesforce-data-server",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", 8080)),
)


async def _run_soql(soql: str) -> list[dict]:
    access_token, instance_url = await get_salesforce_session()
    url = f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/query"

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            url,
            params={"q": soql},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        payload = response.json()

    records = list(payload.get("records", []))

    # TODO: Salesforce paginates query results past 2000 records via
    # nextRecordsUrl — neither tool below needs it yet for a single rep's
    # pipeline, but get_stage_duration_benchmark (org-wide) may eventually.
    if not payload.get("done", True):
        print("[salesforce_mcp_server] WARNING: query results are paginated "
              "and only the first page was fetched — nextRecordsUrl not followed yet.")

    return records


@mcp.tool()
async def get_opportunities_by_rep_name(rep_name: str) -> dict:
    """Return every opportunity belonging to this rep, in this pipeline's
    clean field-name shape (see soql.FIELD_MAP), as {"opportunities": [...]}.

    Scoped by Sales_Rep_Name__c, not OwnerId — every Opportunity in this
    org shares one OwnerId (a shared/integration user), so OwnerId can't
    identify an individual rep. Sales_Rep_Name__c is the real per-rep field.

    Wrapped in a dict rather than returned as a bare list — FastMCP emits
    one MCP content block PER LIST ITEM for bare list[...] return types
    (confirmed directly: a 230-record list came back as 230 separate
    content blocks, silently truncated to 1 by a naive client reading only
    content[0]). Wrapping in a dict keeps the response as a single JSON
    object/content block regardless of list length.
    """
    records = await _run_soql(build_opportunities_by_rep_name_soql(rep_name))
    return {"opportunities": [parse_opportunity_record(r) for r in records]}


@mcp.tool()
async def get_opportunities_by_account(account_id: str) -> dict:
    """Return every opportunity on this Salesforce account ID, regardless
    of owner or open/closed status — used for expansion-whitespace
    detection, a different question than "this rep's own open pipeline."
    Returns {"opportunities": [...]} — see get_opportunities_by_rep_name for
    why this is a dict, not a bare list."""
    records = await _run_soql(build_opportunities_by_account_soql(account_id))
    return {"opportunities": [parse_opportunity_record(r) for r in records]}


@mcp.tool()
async def get_stage_duration_benchmark() -> dict:
    """Org-wide average days-in-stage per stage, across all historically
    closed-won opportunities."""
    records = await _run_soql(build_stage_benchmark_soql())
    return {
        r["stage"]: round(r["avgDays"], 1)
        for r in records
        if r.get("stage") and r.get("avgDays") is not None
    }


@mcp.tool()
async def get_closed_won_attainment(rep_name: str) -> dict:
    """Closed-won ARR for this rep, for quota-attainment calculations:
    {"closed_won_arr_current_month": <num>, "closed_won_arr_trailing_3_months": <num>}.

    current_month = CloseDate in the current calendar month.
    trailing_3_months = CloseDate within the trailing 3 calendar months,
    INCLUSIVE of the current month.

    Scoped by Sales_Rep_Name__c, not OwnerId — see
    get_opportunities_by_rep_name for why.

    Two separate aggregate SOQL queries under the hood (SUM(CASE WHEN...)
    isn't valid SOQL, unlike BigQuery) — see soql.build_attainment_current_month_soql
    and soql.build_attainment_trailing_3_months_soql for details."""
    current_month_records, trailing_records = await asyncio.gather(
        _run_soql(build_attainment_current_month_soql(rep_name)),
        _run_soql(build_attainment_trailing_3_months_soql(rep_name)),
    )
    current_month_arr = current_month_records[0]["closedWonArr"] if current_month_records else None
    trailing_3_months_arr = trailing_records[0]["closedWonArr"] if trailing_records else None
    return {
        "closed_won_arr_current_month": current_month_arr or 0,
        "closed_won_arr_trailing_3_months": trailing_3_months_arr or 0,
    }


@mcp.tool()
async def create_task(account_id: str, owner_id: str, subject: str, description: str) -> dict:
    """
    Create a Salesforce Task anchored to an Account (WhatId), assigned to
    a rep (OwnerId) — used for the expansion-whitespace nudge (see
    account_analysis_agent's expansion_signal). Anchored to the Account
    rather than any specific opportunity since the ask is about the
    account's future, and the triggering Legacy Contract opportunity is
    typically already closed and not part of the rep's active pipeline
    view. Due 7 days out, Status "Not Started", Priority "Normal" — fixed
    conventions, not currently configurable per call.
    """
    access_token, instance_url = await get_salesforce_session()
    url = f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/sobjects/Task/"
    activity_date = (date.today() + timedelta(days=7)).isoformat()

    body = {
        "WhatId": account_id,
        "OwnerId": owner_id,
        "Subject": subject,
        "Description": description,
        "ActivityDate": activity_date,
        "Status": "Not Started",
        "Priority": "Normal",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            url,
            json=body,
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        )
        if response.is_error:
            raise RuntimeError(f"Task creation failed ({response.status_code}): {response.text}")
        return response.json()


if __name__ == "__main__":
    mcp.run(transport="sse")
