"""
salesforce_mcp_server/check_bigquery_labels.py

The original BigQuery export used human-readable Salesforce FIELD LABELS
as column names (e.g. "Opportunity ARR", "Sales Rep Name") — not API
names. Our FIELD_MAP guesses were built against likely API names, which
missed at least one real match (Sales Rep Name -> Sales_Rep_Name__c, not
Owner.Name). This script matches by LABEL instead, against both
Opportunity and Account, and checks whether each match actually has data.

Run from the repo root:
    python -m salesforce_mcp_server.check_bigquery_labels
"""

import asyncio

import httpx

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .describe_fields import describe_object
from .salesforce_auth import get_salesforce_session

SALESFORCE_API_VERSION = "v60.0"
SAMPLE_SIZE = 100

# clean_name -> (BigQuery column label, which object the label implies)
BIGQUERY_LABELS = {
    "opportunity_id":               ("Opportunity ID", "Opportunity"),
    "opportunity_name":              ("Opportunity Name", "Opportunity"),
    "account_id":                    ("Account ID", "Opportunity"),
    "account_name":                  ("Account Name", "Account"),
    "industry":                      ("Account Industry", "Account"),
    "account_segment":               ("Account Segment", "Account"),
    "opportunity_type":              ("Opportunity Type", "Opportunity"),
    "current_stage":                 ("Opportunity Stage", "Opportunity"),
    "forecast_category":             ("Opportunity Forecast Category", "Opportunity"),
    "deal_value_arr":                ("Opportunity ARR", "Opportunity"),
    "discount_pct":                  ("Opportunity Discount", "Opportunity"),
    "created_date":                  ("Opportunity Created Date", "Opportunity"),
    "close_date_target":             ("Opportunity Close Date", "Opportunity"),
    "days_open":                     ("Opportunity Days in Pipeline", "Opportunity"),
    "current_stage_duration_days":   ("Opportunity Days in Stage", "Opportunity"),
    "days_since_last_touch":         ("Opportunity Days Since Last Activity", "Opportunity"),
    "next_step":                     ("Opportunity Next Step", "Opportunity"),
    "risks":                         ("Opportunity Risks", "Opportunity"),
    "cbi_raw_text":                  ("Opportunity CBIs", "Opportunity"),
    "opportunity_manager_notes":     ("Opportunity Manager Notes", "Opportunity"),
    "sales_rep_name":                ("Sales Rep Name", "Opportunity"),
    "opportunity_previous_solution": ("Opportunity Previous Solution", "Opportunity"),
    "contact_name":                  ("Opportunity Contact Name", "Opportunity"),
    "contact_title":                 ("Opportunity Contact Title", "Opportunity"),
}


def _normalize(label: str) -> str:
    return label.lower().replace("opportunity ", "").replace("account ", "").strip()


def _find_by_label(fields: list[dict], target_label: str) -> dict | None:
    target = _normalize(target_label)
    # exact normalized match first, then substring fallback
    for f in fields:
        if _normalize(f["label"]) == target:
            return f
    for f in fields:
        if target in _normalize(f["label"]) or _normalize(f["label"]) in target:
            return f
    return None


def _extract(record: dict, field_path: str):
    value = record
    for part in field_path.split("."):
        if value is None:
            return None
        value = value.get(part)
    return value


async def main():
    opportunity_describe = await describe_object("Opportunity")
    account_describe = await describe_object("Account")
    fields_by_object = {
        "Opportunity": opportunity_describe["fields"],
        "Account": account_describe["fields"],
    }

    matches: dict[str, str] = {}  # clean_name -> resolved API field path
    print(f"{'clean_name':<32} {'BigQuery label':<38} {'Matched Salesforce field'}")
    print("-" * 100)
    for clean_name, (label, object_name) in BIGQUERY_LABELS.items():
        match = _find_by_label(fields_by_object[object_name], label)
        if match is None:
            print(f"{clean_name:<32} {label:<38} NOT FOUND")
            continue
        field_path = match["name"] if object_name == "Opportunity" else f"Account.{match['name']}"
        matches[clean_name] = field_path
        print(f"{clean_name:<32} {label:<38} {field_path}  (label: {match['label']!r})")

    # Now check which of the matched fields actually have data, sampled.
    print(f"\nSampling {SAMPLE_SIZE} Opportunity records to check which matched fields have real data...\n")
    access_token, instance_url = await get_salesforce_session()
    query_fields = sorted(set(matches.values()) | {"Id"})
    soql = f"SELECT {', '.join(query_fields)} FROM Opportunity LIMIT {SAMPLE_SIZE}"

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/query",
            params={"q": soql},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if response.is_error:
            raise RuntimeError(f"Query failed ({response.status_code}): {response.text}")
        records = response.json().get("records", [])

    total = len(records)
    print(f"{'clean_name':<32} {'Matched field':<30} {'Non-null':>10} {'% null':>8}")
    print("-" * 84)
    for clean_name, field_path in matches.items():
        non_null = sum(1 for r in records if _extract(r, field_path) is not None)
        pct_null = round((total - non_null) / total * 100, 1) if total else 0
        flag = "  <-- ALL NULL" if non_null == 0 else ""
        print(f"{clean_name:<32} {field_path:<30} {non_null:>10} {pct_null:>7}%{flag}")


if __name__ == "__main__":
    asyncio.run(main())
