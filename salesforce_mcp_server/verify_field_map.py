"""
salesforce_mcp_server/verify_field_map.py

Checks every single field referenced in soql.FIELD_MAP against the real
Salesforce schema — including relationship traversals (Account.X, Owner.X),
which need their target object's describe, not just Opportunity's.

Run from the repo root:
    python -m salesforce_mcp_server.verify_field_map
"""

import asyncio

from .describe_case_fields import describe_object
from .soql import FIELD_MAP

# Which object a relationship prefix's fields actually live on.
RELATIONSHIP_TARGET_OBJECT = {
    "Account": "Account",
    "Owner": "User",
}


async def main():
    describes: dict[str, dict] = {}
    describes["Opportunity"] = await describe_object("Opportunity")

    # Fetch describes for every related object any FIELD_MAP entry touches.
    for api_field in FIELD_MAP.values():
        if "." in api_field:
            relationship, _ = api_field.split(".", 1)
            target_object = RELATIONSHIP_TARGET_OBJECT.get(relationship)
            if target_object and target_object not in describes:
                describes[target_object] = await describe_object(target_object)

    field_names_by_object = {
        obj_name: {f["name"] for f in describe["fields"]}
        for obj_name, describe in describes.items()
    }

    print(f"\n{'Clean name':<32} {'Salesforce field':<30} {'Status'}")
    print("-" * 80)

    missing = []
    for clean_name, api_field in FIELD_MAP.items():
        if "." in api_field:
            relationship, field_name = api_field.split(".", 1)
            target_object = RELATIONSHIP_TARGET_OBJECT.get(relationship, "?")
            exists = field_name in field_names_by_object.get(target_object, set())
        else:
            field_name = api_field
            exists = field_name in field_names_by_object["Opportunity"]

        status = "OK" if exists else "MISSING"
        if not exists:
            missing.append((clean_name, api_field))
        print(f"{clean_name:<32} {api_field:<30} {status}")

    print("-" * 80)
    if missing:
        print(f"\n{len(missing)} field(s) do NOT exist in this org's schema:")
        for clean_name, api_field in missing:
            print(f"  - {clean_name} -> {api_field}")
    else:
        print("\nAll fields in FIELD_MAP exist in this org's schema.")


if __name__ == "__main__":
    asyncio.run(main())
