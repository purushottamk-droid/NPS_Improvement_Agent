"""
salesforce_mcp_server/describe_fields.py

One-off script to pull the REAL field list for Opportunity (and Account,
for the account_segment lookup) from Salesforce's describe API, so the
placeholder names in soql.FIELD_MAP can be replaced with actual field API
names instead of guesses.

Run from the repo root:
    python -m salesforce_mcp_server.describe_fields
"""

import asyncio
import os

import httpx

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .salesforce_auth import get_salesforce_session

SALESFORCE_API_VERSION = os.environ.get("SALESFORCE_API_VERSION", "v60.0")

# Keywords to flag as "likely relevant" when scanning custom fields —
# matched loosely against label/field name to help spot FIELD_MAP candidates.
RELEVANT_KEYWORDS = [
    "discount", "days in stage", "days_in_stage", "days since last activity",
    "days_since_last_activity", "days in pipeline", "days_in_pipeline",
    "risk", "cbi", "manager note", "manager_note", "previous solution",
    "previous_solution", "contact name", "contact_name", "contact title",
    "contact_title", "segment",
]


async def describe_object(object_name: str) -> dict:
    access_token, instance_url = await get_salesforce_session()
    url = f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/sobjects/{object_name}/describe"

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
        if response.is_error:
            raise RuntimeError(f"Describe call for {object_name} failed ({response.status_code}): {response.text}")
        return response.json()


def _print_fields(object_name: str, describe_result: dict):
    fields = describe_result.get("fields", [])
    custom_fields = [f for f in fields if f.get("custom")]
    standard_fields = [f for f in fields if not f.get("custom")]

    print(f"\n{'=' * 60}")
    print(f"{object_name} — {len(fields)} total fields ({len(custom_fields)} custom)")
    print(f"{'=' * 60}")

    print(f"\n-- Custom fields (all {len(custom_fields)}) --")
    for f in sorted(custom_fields, key=lambda f: f["name"]):
        print(f"  {f['name']:<40} label={f['label']!r:<45} type={f['type']}")

    print(f"\n-- Standard fields matching our RELEVANT_KEYWORDS (out of {len(standard_fields)} standard) --")
    for f in sorted(standard_fields, key=lambda f: f["name"]):
        label_lower = f.get("label", "").lower()
        name_lower = f["name"].lower()
        if any(kw in label_lower or kw in name_lower for kw in RELEVANT_KEYWORDS):
            print(f"  {f['name']:<40} label={f['label']!r:<45} type={f['type']}")


async def main():
    opportunity_describe = await describe_object("Opportunity")
    _print_fields("Opportunity", opportunity_describe)

    account_describe = await describe_object("Account")
    _print_fields("Account", account_describe)

    print(f"\n{'=' * 60}")
    print("Cross-reference the custom fields above against soql.FIELD_MAP's")
    print("placeholder names (Discount__c, Days_in_Stage__c, Risks__c, CBIs__c,")
    print("Manager_Notes__c, Previous_Solution__c, Contact_Name__c,")
    print("Contact_Title__c, Account.Segment__c) and update FIELD_MAP accordingly.")


if __name__ == "__main__":
    asyncio.run(main())