"""Users tools - deactivate users, export with custom fields."""

import asyncio
import json
from datetime import datetime

import aiohttp
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
    display_dataframe_results,
    file_uploader,
    tool_header,
)

st.header("Users")
if not check_token():
    st.stop()

tab1, tab2 = st.tabs(["Deactivate Users", "Export User Custom Fields"])


# ─── Deactivate Users ────────────────────────────────────────────────────────
with tab1:
    tool_header(
        "Bulk Deactivate Users",
        "Deactivate users in bulk using the upsert job system. "
        "Users are processed in chunks of 2,000.",
        requires_csv=True,
    )

    id_type = st.radio("Identify users by:", ["email", "user_id"], key="deactivate_id_type")
    validate_only = st.checkbox("Validate only (dry run)", value=True, key="deactivate_validate")

    required_col = "email" if id_type == "email" else "user_id"
    df = file_uploader(
        f"Upload CSV with '{required_col}' column",
        required_columns=[required_col],
        key="deactivate_users_csv",
    )

    if df is not None and st.button("Deactivate Users", key="run_deactivate"):
        token = get_token()
        records = df.fillna("").to_dict("records")
        headers = get_headers(token)

        # Map users
        mapped = []
        for row in records:
            if id_type == "user_id":
                val = str(row.get("user_id", "")).strip()
                if val:
                    mapped.append({"user": {"user_id": val, "status": "deactivated"}})
            else:
                val = str(row.get("email", "")).strip()
                if val:
                    mapped.append({"user": {"username": val, "status": "deactivated"}})

        if not mapped:
            st.error("No valid users found.")
        else:
            chunks = [mapped[i:i + 2000] for i in range(0, len(mapped), 2000)]
            progress = st.progress(0, text=f"Processing {len(chunks)} chunk(s)...")
            all_results = []

            for i, chunk in enumerate(chunks):
                try:
                    # Initialize job
                    resp = requests.post(
                        f"{BASE_URL}/users/v1/users/upsert/jobs",
                        json={"users": chunk}, headers=headers, timeout=30,
                    )
                    resp.raise_for_status()
                    job_id = resp.json()["job_id"]

                    # Start job
                    resp = requests.post(
                        f"{BASE_URL}/users/v1/users/upsert/jobs/{job_id}",
                        json={"origin": {"source": "SOURCE_UNSPECIFIED"}, "validate_only": validate_only},
                        headers=headers, timeout=30,
                    )
                    resp.raise_for_status()
                    result_id = resp.json()["job_id"]

                    # Get results
                    resp = requests.get(
                        f"{BASE_URL}/users/v1/users/upsert/jobs/{result_id}",
                        headers={"accept": "application/json", "authorization": f"Bearer {token}"},
                        timeout=30,
                    )
                    all_results.append({
                        "chunk": i + 1,
                        "users": len(chunk),
                        "status": "SUCCESS",
                        "job_id": result_id,
                        "details": json.dumps(resp.json())[:500],
                    })
                except Exception as e:
                    all_results.append({
                        "chunk": i + 1,
                        "users": len(chunk),
                        "status": "ERROR",
                        "job_id": "",
                        "details": str(e),
                    })
                progress.progress((i + 1) / len(chunks))

            progress.empty()
            mode = "VALIDATION" if validate_only else "EXECUTION"
            st.success(f"{mode} complete for {len(mapped)} users.")

            results_df = pd.DataFrame(all_results)
            display_dataframe_results(results_df, "deactivation_results.csv", "Job Results")


# ─── Export User Custom Fields ────────────────────────────────────────────────
with tab2:
    tool_header(
        "Export Users with Custom Fields",
        "Export all users from your organization including custom field values. "
        "Custom fields are fetched individually per user and added as columns.",
    )

    if st.button("Export Users", key="run_export_users"):
        token = get_token()
        progress = st.progress(0, text="Fetching custom field definitions...")

        async def _export_users():
            session, _ = create_async_session(token, concurrency=10)
            try:
                # Step 1: Get custom fields
                async with session.post(
                    f"{BASE_URL}/users/v1/fields/list",
                    json={},
                ) as resp:
                    resp.raise_for_status()
                    fields = (await resp.json()).get("fields", [])

                progress.progress(0.1, text=f"Found {len(fields)} custom fields. Fetching users...")

                # Step 2: Fetch users from feed
                users = []
                url = f"{BASE_URL}/feed/users"
                while url:
                    async with session.get(url) as resp:
                        resp.raise_for_status()
                        body = await resp.json()
                    users.extend(body.get("data", []))
                    np = body.get("metadata", {}).get("next_page")
                    url = (np if np.startswith("http") else f"{BASE_URL}{np}") if np else None
                    progress.progress(
                        min(0.1 + len(users) / max(len(users) + 1, 100) * 0.3, 0.4),
                        text=f"Fetched {len(users):,} users...",
                    )

                if not users:
                    return [], []

                # Step 3: Fetch attributes per user
                progress.progress(0.4, text=f"Fetching attributes for {len(users)} users...")
                semaphore = asyncio.Semaphore(10)
                completed = 0

                async def fetch_attrs(user):
                    nonlocal completed
                    uid = user.get("id", user.get("user_id", ""))
                    uuid_only = uid.replace("user_", "") if uid.startswith("user_") else uid
                    async with semaphore:
                        try:
                            async with session.get(f"{BASE_URL}/users/v1/users/{uuid_only}/attributes") as resp:
                                completed += 1
                                progress.progress(0.4 + completed / len(users) * 0.5, text=f"Attributes {completed}/{len(users)}...")
                                if resp.status == 200:
                                    data = await resp.json()
                                    return uid, data.get("attributes", [])
                                return uid, []
                        except Exception:
                            completed += 1
                            return uid, []

                tasks = [fetch_attrs(u) for u in users]
                attr_results = await asyncio.gather(*tasks)
                attrs_by_user = {}
                for uid, attrs in attr_results:
                    d = {}
                    for a in attrs:
                        fid = a.get("field_id")
                        vals = a.get("attribute_values", [])
                        val = ""
                        if vals:
                            v = vals[0]
                            val = v.get("string_value") or v.get("number_value") or v.get("bool_value") or v.get("date_value") or ""
                        if fid:
                            d[fid] = val
                    attrs_by_user[uid] = d

                return users, fields, attrs_by_user
            finally:
                await session.close()

        result = run_async(_export_users())
        progress.empty()

        if len(result) == 3:
            users, fields, attrs_by_user = result
        else:
            users, fields, attrs_by_user = [], [], {}

        if users:
            rows = []
            for user in users:
                uid = user.get("id", user.get("user_id", ""))
                row = {}
                for k, v in user.items():
                    row[k] = json.dumps(v) if isinstance(v, (dict, list)) else v
                user_attrs = attrs_by_user.get(uid, {})
                for f in fields:
                    fname = f.get("name", f.get("id", ""))
                    row[fname] = user_attrs.get(f.get("id", ""), "")
                rows.append(row)

            df = pd.DataFrame(rows)
            display_dataframe_results(df, "users_with_custom_fields.csv", f"Exported {len(df):,} Users")
        else:
            st.info("No users found.")
