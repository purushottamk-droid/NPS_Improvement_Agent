import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client

async def main():
    async with sse_client("http://localhost:8080/sse") as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            accounts = await session.call_tool("debug_list_accounts", {})
            print("Accounts:")
            print(accounts.content[0].text)

            opportunities = await session.call_tool("debug_list_opportunity_account_ids", {})
            print("\nOpportunities:")
            print(opportunities.content[0].text)

asyncio.run(main())