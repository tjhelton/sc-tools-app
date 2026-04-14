"""Organizations tools - export contractor companies."""

import pandas as pd
import requests
import streamlit as st

from core.api import BASE_URL, get_headers, get_token
from core.ui import check_token, display_dataframe_results, tool_header

st.header("Organizations")
if not check_token():
    st.stop()

tool_header(
    "Export Contractor Companies",
    "Export all contractor companies from your organization, including nested "
    "attributes flattened into columns.",
)


def flatten_record(record, parent_key="", sep="."):
    """Flatten nested dicts/lists into dot-notation keys."""
    items = {}
    for k, v in record.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(flatten_record(v, new_key, sep))
        elif isinstance(v, list):
            if v and all(isinstance(i, (str, int, float, bool)) for i in v):
                items[new_key] = " | ".join(str(i) for i in v)
            elif v:
                for i, item in enumerate(v):
                    if isinstance(item, dict):
                        items.update(flatten_record(item, f"{new_key}.{i}", sep))
                    else:
                        items[f"{new_key}.{i}"] = item
            else:
                items[new_key] = ""
        else:
            items[new_key] = v
    return items


if st.button("Export Companies", key="run_export_companies"):
    token = get_token()
    progress = st.progress(0, text="Fetching contractor companies...")

    headers = get_headers(token)
    all_companies = []
    page_token = None
    page = 0

    while True:
        payload = {"page_size": 100}
        if page_token:
            payload["page_token"] = page_token

        try:
            resp = requests.post(
                f"{BASE_URL}/companies/v1beta/companies",
                json=payload,
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            body = resp.json()
        except Exception as e:
            st.error(f"API error: {e}")
            break

        companies = body.get("contractor_company_list", [])
        all_companies.extend(companies)
        page += 1

        total_count = body.get("total_count", len(all_companies))
        if total_count > 0:
            progress.progress(
                min(0.95, len(all_companies) / total_count),
                text=f"Fetched {len(all_companies):,} of {total_count:,} companies...",
            )

        page_token = body.get("next_page_token")
        if not page_token:
            break

    progress.empty()

    if all_companies:
        rows = [flatten_record(c) for c in all_companies]
        df = pd.DataFrame(rows)
        display_dataframe_results(
            df, "contractor_companies.csv",
            f"Exported {len(df):,} Contractor Companies",
        )
    else:
        st.info("No contractor companies found.")
