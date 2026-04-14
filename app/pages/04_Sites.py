"""Sites tools - create, delete, find inactive, update user access."""

import asyncio
import time
from datetime import datetime
from urllib.parse import urlencode

import pandas as pd
import requests
import streamlit as st

from core.api import (
    BASE_URL,
    create_async_session,
    get_headers,
    get_token,
    run_async,
)
from core.ui import (
    check_token,
    confirm_destructive,
    display_dataframe_results,
    display_results,
    file_uploader,
    tool_header,
)

st.header("Sites")
if not check_token():
    st.stop()

tab1, tab2, tab3, tab4 = st.tabs([
    "Create Sites", "Delete Sites", "Find Inactive Sites", "Update Site Users",
])


# ─── Create Sites ────────────────────────────────────────────────────────────
with tab1:
    tool_header(
        "Bulk Create Sites",
        "Create sites in bulk. Supports parent site references and meta labels.",
        requires_csv=True,
        csv_columns=["name"],
    )
    st.info("Optional columns: `parent` (parent site ID), `meta_label` (site label/tier)")

    df = file_uploader("Upload CSV", required_columns=["name"], key="create_sites_csv")
    if df is not None and st.button("Create Sites", key="run_create_sites"):
        token = get_token()
        records = df.fillna("").to_dict("records")
        progress = st.progress(0, text="Creating sites...")
        results = []

        for i, row in enumerate(records):
            name = str(row["name"]).strip()
            parent = str(row.get("parent", "")).strip()
            meta_label = str(row.get("meta_label", "")).strip()
            payload = {"name": name}
            if meta_label:
                payload["meta_label"] = meta_label
            if parent:
                payload["parent_id"] = parent

            try:
                resp = requests.post(
                    f"{BASE_URL}/directory/v1/folder",
                    json=payload,
                    headers={"authorization": f"Bearer {token}"},
                    timeout=30,
                )
                resp.raise_for_status()
                results.append({"name": name, "status": "SUCCESS", "response": resp.text[:200]})
            except Exception as e:
                results.append({"name": name, "status": "ERROR", "response": str(e)})
            progress.progress((i + 1) / len(records))

        progress.empty()
        display_results(results, "create_sites_results.csv")


# ─── Delete Sites ────────────────────────────────────────────────────────────
with tab2:
    tool_header(
        "Bulk Delete Sites",
        "Delete sites in batches of 50. Uses cascade_up=true. **This cannot be undone.**",
        requires_csv=True,
        csv_columns=["siteId"],
    )

    df = file_uploader("Upload CSV", required_columns=["siteId"], key="delete_sites_csv")
    if df is not None:
        confirmed = confirm_destructive(
            f"You are about to **delete {len(df):,} sites**. This cannot be undone.",
            "delete_sites",
        )
        if confirmed and st.button("Delete Sites", key="run_delete_sites", type="primary"):
            token = get_token()
            site_ids = [str(r).strip() for r in df["siteId"].tolist()]
            batch_size = 50
            batches = [site_ids[i:i + batch_size] for i in range(0, len(site_ids), batch_size)]
            progress = st.progress(0, text="Deleting sites...")
            results = []

            for i, batch in enumerate(batches):
                params = [("folder_ids", sid) for sid in batch]
                params.append(("cascade_up", "true"))
                url = f"{BASE_URL}/directory/v1/folders?{urlencode(params)}"
                try:
                    resp = requests.delete(
                        url,
                        headers={"authorization": f"Bearer {token}", "accept": "application/json"},
                        timeout=30,
                    )
                    resp.raise_for_status()
                    for sid in batch:
                        results.append({"site_id": sid, "batch": i + 1, "status": "SUCCESS", "error": ""})
                except Exception as e:
                    for sid in batch:
                        results.append({"site_id": sid, "batch": i + 1, "status": "ERROR", "error": str(e)})
                progress.progress((i + 1) / len(batches))
                time.sleep(0.2)

            progress.empty()
            display_results(results, "delete_sites_results.csv")


# ─── Find Inactive Sites ─────────────────────────────────────────────────────
with tab3:
    tool_header(
        "Find Inactive Sites",
        "Identify sites that have never had an inspection. Fetches all inspections and sites, "
        "then cross-references to find sites with no activity.",
    )

    if st.button("Find Inactive Sites", key="run_inactive_sites"):
        token = get_token()
        progress = st.progress(0, text="Fetching inspections and sites...")

        async def _find_inactive():
            session, _ = create_async_session(token)
            try:
                # Fetch inspections
                inspections = []
                url = f"{BASE_URL}/feed/inspections?archived=false&completed=both"
                while url:
                    async with session.get(url) as resp:
                        resp.raise_for_status()
                        body = await resp.json()
                    inspections.extend(body.get("data", []))
                    metadata = body.get("metadata", {})
                    remaining = metadata.get("remaining_records", 0)
                    total_est = len(inspections) + remaining
                    pct = (len(inspections) / total_est * 0.5) if total_est > 0 else 0
                    progress.progress(min(pct, 0.49), text=f"Fetched {len(inspections):,} inspections...")
                    next_page = metadata.get("next_page")
                    url = (next_page if next_page.startswith("http") else f"{BASE_URL}{next_page}") if next_page else None

                # Fetch sites
                progress.progress(0.5, text="Fetching sites...")
                sites = []
                url = f"{BASE_URL}/directory/v1/folders?page_size=1500"
                while url:
                    async with session.get(url) as resp:
                        resp.raise_for_status()
                        body = await resp.json()
                    sites.extend(body.get("folders", []))
                    npt = body.get("next_page_token")
                    url = f"{BASE_URL}/directory/v1/folders?page_size=1500&page_token={npt}" if npt else None
                    progress.progress(0.75, text=f"Fetched {len(sites):,} sites...")

                # Cross reference
                progress.progress(0.9, text="Analyzing...")
                sites_with_activity = {i.get("site_id") for i in inspections if i.get("site_id")}
                inactive = [s for s in sites if s.get("id") and s["id"] not in sites_with_activity]

                return sites, inspections, inactive
            finally:
                await session.close()

        sites, inspections, inactive = run_async(_find_inactive())
        progress.empty()

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Sites", f"{len(sites):,}")
        col2.metric("Sites with Activity", f"{len(sites) - len(inactive):,}")
        col3.metric("Inactive Sites", f"{len(inactive):,}")

        if inactive:
            df = pd.json_normalize(inactive, sep="_")
            display_dataframe_results(df, "inactive_sites.csv", "Inactive Sites")


# ─── Update Site Users ───────────────────────────────────────────────────────
with tab4:
    tool_header(
        "Update Site User Access",
        "Bulk update user site access using the upsert job system. "
        "Removes users from specified sites.",
        requires_csv=True,
        csv_columns=["email", "site_id"],
    )

    validate_only = st.checkbox("Validate only (dry run)", value=True, key="site_users_validate")
    df = file_uploader("Upload CSV", required_columns=["email", "site_id"], key="update_site_users_csv")

    if df is not None and st.button("Update Site Users", key="run_update_site_users"):
        token = get_token()
        records = df.fillna("").to_dict("records")
        headers = get_headers(token)

        with st.spinner("Preparing upsert job..."):
            mapped = []
            for row in records:
                email = str(row["email"]).strip()
                site = str(row["site_id"]).strip()
                if email and site:
                    mapped.append({
                        "user": {
                            "sites": {"remove": [{"name": "*"}, {"id": site}]},
                            "username": email,
                        }
                    })

            if not mapped:
                st.error("No valid records to process.")
            else:
                # Initialize job
                resp = requests.post(
                    f"{BASE_URL}/users/v1/users/upsert/jobs",
                    json={"users": mapped},
                    headers=headers,
                    timeout=30,
                )
                resp.raise_for_status()
                job_id = resp.json()["job_id"]
                st.info(f"Job initialized: {job_id}")

                # Start job
                resp = requests.post(
                    f"{BASE_URL}/users/v1/users/upsert/jobs/{job_id}",
                    json={"origin": {"source": "SOURCE_UNSPECIFIED"}, "validate_only": validate_only},
                    headers=headers,
                    timeout=30,
                )
                resp.raise_for_status()
                result_id = resp.json()["job_id"]

                # Get results
                resp = requests.get(
                    f"{BASE_URL}/users/v1/users/upsert/jobs/{result_id}",
                    headers={"accept": "application/json", "authorization": f"Bearer {token}"},
                    timeout=30,
                )
                st.json(resp.json())
                mode = "VALIDATION" if validate_only else "EXECUTION"
                st.success(f"{mode} job completed. Job ID: {result_id}")
