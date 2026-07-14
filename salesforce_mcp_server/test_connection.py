"""
salesforce_mcp_server/test_connection.py

Standalone script to verify the JWT Bearer flow works against a real
Salesforce org, before wiring this into the full MCP server or deploying
it. Run from the repo root:

    python -m salesforce_mcp_server.test_connection

Requires these env vars set (e.g. via a local .env file, loaded below if
present):
  SALESFORCE_JWT_CLIENT_ID
  SALESFORCE_JWT_SUBJECT
  SALESFORCE_JWT_PRIVATE_KEY
  SALESFORCE_JWT_AUDIENCE   (optional, defaults to production)
"""

import asyncio

import httpx

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # fine if not installed — env vars can be exported directly instead

from .salesforce_auth import get_salesforce_session


async def main():
    print("Requesting a Salesforce session via JWT Bearer flow...")
    access_token, instance_url = await get_salesforce_session()

    print("Token exchange succeeded.")
    print(f"  instance_url: {instance_url}")
    print(f"  access_token length: {len(access_token)} chars (not printed — treat it as a live credential)")

    print("\nConfirming the token actually works with a trivial SOQL query...")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{instance_url}/services/data/v60.0/query",
            params={"q": "SELECT Id, Name FROM Organization LIMIT 1"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        payload = response.json()

    org_name = payload["records"][0]["Name"] if payload.get("records") else "(unknown)"
    print(f"API call succeeded — connected to org: {org_name}")


if __name__ == "__main__":
    asyncio.run(main())
