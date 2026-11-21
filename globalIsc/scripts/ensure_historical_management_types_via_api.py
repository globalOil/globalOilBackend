#!/usr/bin/env python3
"""Ensure the fixed management-type catalog used by the historical ETL.

The source workbooks contain no management-type value.  This script creates
only the catalog options; it intentionally never assigns one to a migrated
historical batch.
"""
import argparse
import json

from load_global_oil_via_api import Api


MANAGEMENT_TYPES = ("Comercial", "Postventa", "PQR")


def norm(value):
    return " ".join(str(value or "").split()).casefold()


def patch(api, path, payload):
    token = api.session.cookies.get("csrftoken")
    response = api._request(
        "patch",
        path,
        json=payload,
        headers={"X-CSRFToken": token or "", "Referer": api.base_url},
    )
    if not response.ok:
        raise RuntimeError(f"API PATCH {path} ({response.status_code}): {response.text}")
    return response.json()


def main():
    parser = argparse.ArgumentParser(description="Configura los tipos de gestión base de la ETL histórica.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    api = Api(args.base_url, args.email, args.password)
    rows = api.get("technical-catalogs/sample-management-types/", {"incluir_eliminados": "true", "page_size": 1000})
    by_name = {norm(row.get("nombre")): row for row in rows}
    changes = {"created": [], "updated": [], "unchanged": []}

    for name in MANAGEMENT_TYPES:
        payload = {
            "nombre": name,
            "dias_habiles": 0,
            "dias_calendario": 0,
            "aplica_a_todos": True,
            "activo": True,
        }
        existing = by_name.get(norm(name))
        if not existing:
            api.post("technical-catalogs/sample-management-types/", payload)
            changes["created"].append(name)
            continue

        if existing.get("deleted_at") is not None:
            api.post(f"technical-catalogs/sample-management-types/{existing['id']}/restore/", {})
            existing["deleted_at"] = None

        changes_needed = {
            key: value for key, value in payload.items()
            if existing.get(key) != value
        }
        if changes_needed:
            patch(api, f"technical-catalogs/sample-management-types/{existing['id']}/", changes_needed)
            changes["updated"].append(name)
        else:
            changes["unchanged"].append(name)

    print(json.dumps({"management_types": list(MANAGEMENT_TYPES), **changes}, ensure_ascii=False))


if __name__ == "__main__":
    main()
