"""Issues tools - export public links, export issue relations."""

import asyncio

import pandas as pd
import requests
import streamlit as st

from core.api import BASE_URL, create_async_session, get_headers, get_token, run_async
from core.ui import (
    check_token,
    display_dataframe_results,
    display_results,
    file_uploader,
    tool_header,
)

st.header("Issues")
if not check_token():
    st.stop()

tab1, tab2 = st.tabs(["Export Public Links", "Export Relations"])


# ─── Export Public Links ────────────────────────────────────────────────────
with tab1:
    tool_header(
        "Export Issue Public Links",
        "Generate public shareable links for issues in bulk.",
        requires_csv=True,
        csv_columns=["issue_id"],
    )

    df = file_uploader("Upload CSV", required_columns=["issue_id"], key="issue_links_csv")
    if df is not None and st.button("Export Links", key="run_issue_links"):
        token = get_token()
        records = df.to_dict("records")
        progress = st.progress(0, text="Generating public links...")
        results = []

        async def _export_links():
            session, _ = create_async_session(token, concurrency=10)
            semaphore = asyncio.Semaphore(10)
            completed = 0
            total = len(records)

            async def fetch_link(row):
                nonlocal completed
                issue_id = str(row["issue_id"]).strip()
                async with semaphore:
                    try:
                        async with session.post(
                            f"{BASE_URL}/tasks/v1/shared_link/{issue_id}/web_report"
                        ) as resp:
                            completed += 1
                            progress.progress(completed / total)
                            if resp.status == 200:
                                data = await resp.json()
                                return {
                                    "issue_id": issue_id,
                                    "url": data.get("url", ""),
                                    "status": "SUCCESS",
                                    "error": "",
                                }
                            text = await resp.text()
                            return {
                                "issue_id": issue_id,
                                "url": "",
                                "status": "ERROR",
                                "error": f"HTTP {resp.status}: {text[:200]}",
                            }
                    except Exception as e:
                        completed += 1
                        return {
                            "issue_id": issue_id,
                            "url": "",
                            "status": "ERROR",
                            "error": str(e),
                        }

            tasks = [fetch_link(r) for r in records]
            return await asyncio.gather(*tasks)

        try:
            results = list(run_async(_export_links()))
        finally:
            progress.empty()

        display_results(results, "issue_public_links.csv")


# ─── Export Issue Relations ─────────────────────────────────────────────────
with tab2:
    tool_header(
        "Export Issue Relations",
        "Export all issue relationships across the organization. Shows how issues "
        "relate to inspections, actions, and assets.",
    )

    if st.button("Export Relations", key="run_issue_relations"):
        token = get_token()
        progress = st.progress(0, text="Fetching issue relations...")

        async def _export_relations():
            session, _ = create_async_session(token)
            try:
                all_data = []
                url = f"{BASE_URL}/feed/issue_relations?limit=100"
                page = 0

                while url:
                    async with session.get(url) as resp:
                        resp.raise_for_status()
                        body = await resp.json()

                    data = body.get("data", [])
                    all_data.extend(data)
                    page += 1
                    progress.progress(
                        min(0.95, page * 0.05),
                        text=f"Fetched {len(all_data):,} relations (page {page})...",
                    )

                    next_page = body.get("metadata", {}).get("next_page")
                    if next_page:
                        url = next_page if next_page.startswith("http") else f"{BASE_URL}{next_page}"
                    else:
                        url = None

                return all_data
            finally:
                await session.close()

        relations = run_async(_export_relations())
        progress.empty()

        if relations:
            df = pd.DataFrame(relations)
            display_dataframe_results(df, "issue_relations.csv", f"Exported {len(relations):,} Issue Relations")
        else:
            st.info("No issue relations found.")
