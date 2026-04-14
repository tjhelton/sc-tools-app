"""Groups tools - create groups, export group assignees."""

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

st.header("Groups")
if not check_token():
    st.stop()

tab1, tab2 = st.tabs(["Create Groups", "Export Group Assignees"])


# ─── Create Groups ───────────────────────────────────────────────────────────
with tab1:
    tool_header(
        "Bulk Create Groups",
        "Create groups in bulk from a CSV file.",
        requires_csv=True,
        csv_columns=["name"],
    )

    df = file_uploader("Upload CSV", required_columns=["name"], key="create_groups_csv")
    if df is not None and st.button("Create Groups", key="run_create_groups"):
        token = get_token()
        records = df.to_dict("records")
        progress = st.progress(0, text="Creating groups...")
        results = []

        for i, row in enumerate(records):
            name = str(row["name"]).strip()
            try:
                resp = requests.post(
                    f"{BASE_URL}/groups",
                    json={"name": name},
                    headers=get_headers(token),
                    timeout=30,
                )
                data = resp.json()
                results.append({
                    "name": name,
                    "status": "SUCCESS" if "id" in data else "ERROR",
                    "group_id": data.get("id", ""),
                    "error": "" if "id" in data else str(data),
                })
            except Exception as e:
                results.append({"name": name, "status": "ERROR", "group_id": "", "error": str(e)})
            progress.progress((i + 1) / len(records))

        progress.empty()
        display_results(results, "create_groups_results.csv")


# ─── Export Group Assignees ──────────────────────────────────────────────────
with tab2:
    tool_header(
        "Export Group Assignees",
        "Export all group members across all groups. Shows user details "
        "including name, email, and user ID for each group membership.",
    )

    if st.button("Export Assignees", key="run_export_assignees"):
        token = get_token()
        progress = st.progress(0, text="Fetching groups...")

        async def _export_assignees():
            session, _ = create_async_session(token, concurrency=25)
            try:
                # Fetch all groups
                async with session.get(f"{BASE_URL}/groups") as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                groups = data.get("groups", [])
                progress.progress(0.1, text=f"Found {len(groups)} groups. Fetching members...")

                semaphore = asyncio.Semaphore(25)
                all_assignees = []
                completed = 0
                total = len(groups)

                async def fetch_group_users(group):
                    nonlocal completed
                    gid = group["id"]
                    gname = group.get("name", "Unknown")
                    users = []
                    offset = 0

                    async with semaphore:
                        while True:
                            url = f"{BASE_URL}/groups/{gid}/users?limit=1000&offset={offset}"
                            try:
                                async with session.get(url) as resp:
                                    resp.raise_for_status()
                                    data = await resp.json()
                                page_users = data.get("users", [])
                                if not page_users:
                                    break
                                for u in page_users:
                                    users.append({
                                        "group_id": gid,
                                        "group_name": gname,
                                        "user_id": u.get("user_id", ""),
                                        "user_uuid": u.get("id", ""),
                                        "firstname": u.get("firstname", ""),
                                        "lastname": u.get("lastname", ""),
                                        "email": u.get("email", ""),
                                    })
                                offset += 1000
                                if len(page_users) < 1000:
                                    break
                            except Exception:
                                break

                    completed += 1
                    progress.progress(0.1 + completed / total * 0.85)
                    return users

                tasks = [fetch_group_users(g) for g in groups]
                results = await asyncio.gather(*tasks)
                for users in results:
                    all_assignees.extend(users)

                return all_assignees
            finally:
                await session.close()

        assignees = run_async(_export_assignees())
        progress.empty()

        if assignees:
            df = pd.DataFrame(assignees)
            display_dataframe_results(df, "group_assignees.csv", f"Exported {len(assignees):,} Group Memberships")
        else:
            st.info("No group assignees found.")
