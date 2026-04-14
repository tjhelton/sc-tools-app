"""Actions tools - export, update status, delete, manage schedules."""

import asyncio
import csv
import io
import json
import math
import time
from datetime import datetime

import aiohttp
import pandas as pd
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

st.header("Actions")
if not check_token():
    st.stop()

PRIORITY_MAP = {
    "58941717-817f-4c7c-a6f6-5cd05e2bbfde": "None",
    "16ba4717-adc9-4d48-bf7c-044cfe0d2727": "Low",
    "ce87c58a-eeb2-4fde-9dc4-c6e85f1f4055": "Medium",
    "02eb40c1-4f46-40c5-be16-d32941c96ec9": "High",
}

ACTION_STATUSES = {
    "17e793a1-26a3-4ecd-99ca-f38ecc6eaa2e": "To do",
    "20ce0cb1-387a-47d4-8c34-bc6fd3be0e27": "In progress",
    "7223d809-553e-4714-a038-62dc98f3fbf3": "Complete",
    "06308884-41c2-4ee0-9da7-5676647d3d75": "Can't do",
}

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Export Actions", "Update Status", "Delete Actions", "Delete Schedules", "Stop Recurrence"]
)

# ─── Export Actions ──────────────────────────────────────────────────────────
with tab1:
    tool_header(
        "Export All Actions",
        "Exports every action in your organization to CSV with full details "
        "including assignees, priorities, templates, sites, and schedule references.",
    )

    if st.button("Export Actions", key="export_actions"):
        token = get_token()
        progress = st.progress(0, text="Fetching total count...")
        status_text = st.empty()

        async def _export_actions():
            session, _ = create_async_session(token, concurrency=10)
            try:
                # Get total count
                async with session.post(
                    f"{BASE_URL}/tasks/v1/actions/list",
                    json={"page_size": 1, "offset": 0},
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    total = data.get("total", 0)

                if total == 0:
                    return []

                status_text.text(f"Found {total:,} actions. Fetching...")
                page_size = 1000
                total_pages = math.ceil(total / page_size)
                offsets = [i * page_size for i in range(total_pages)]
                semaphore = asyncio.Semaphore(10)
                all_actions = []
                completed = 0

                async def fetch_page(offset):
                    nonlocal completed
                    async with semaphore:
                        async with session.post(
                            f"{BASE_URL}/tasks/v1/actions/list",
                            json={"page_size": page_size, "offset": offset},
                        ) as r:
                            if r.status != 200:
                                return []
                            d = await r.json()
                            completed += 1
                            progress.progress(
                                completed / total_pages,
                                text=f"Fetching page {completed}/{total_pages}...",
                            )
                            return d.get("actions", [])

                tasks = [fetch_page(o) for o in offsets]
                results = await asyncio.gather(*tasks)
                for page in results:
                    all_actions.extend(page)

                return all_actions
            finally:
                await session.close()

        def parse_action(action):
            task = action.get("task", {})
            creator = task.get("creator", {})
            inspection = task.get("inspection", {})
            inspection_item = task.get("inspection_item", {})
            site = task.get("site", {})
            status = task.get("status", {})
            action_type = action.get("type", {})

            assignee_names = []
            for collab in task.get("collaborators", []):
                if collab.get("collaborator_type") == "GROUP":
                    name = collab.get("group", {}).get("name", "")
                else:
                    user = collab.get("user", {})
                    name = f"{user.get('firstname', '')} {user.get('lastname', '')}".strip()
                if name:
                    assignee_names.append(name)

            schedule_id = ""
            for ref in task.get("references", []):
                if ref.get("type") == "SCHEDULE":
                    schedule_id = ref.get("id", "")
                    break

            return {
                "action_id": task.get("task_id", ""),
                "unique_id": task.get("unique_id", ""),
                "creator_name": f"{creator.get('firstname', '')} {creator.get('lastname', '')}".strip(),
                "title": task.get("title", ""),
                "description": task.get("description", ""),
                "created_at": task.get("created_at", ""),
                "due_at": task.get("due_at", ""),
                "priority": PRIORITY_MAP.get(task.get("priority_id", ""), "Unknown"),
                "status": status.get("label", ""),
                "assignees": ", ".join(assignee_names),
                "template_id": task.get("template_id", ""),
                "inspection_id": inspection.get("inspection_id", ""),
                "site_id": site.get("id", ""),
                "site_name": site.get("name", ""),
                "modified_at": task.get("modified_at", ""),
                "completed_at": task.get("completed_at", ""),
                "action_type": action_type.get("name", ""),
                "schedule_id": schedule_id,
            }

        raw = run_async(_export_actions())
        progress.empty()
        status_text.empty()

        if not raw:
            st.info("No actions found.")
        else:
            rows = [parse_action(a) for a in raw]
            df = pd.DataFrame(rows)
            display_dataframe_results(df, "actions_export.csv", f"Exported {len(df):,} Actions")


# ─── Update Action Status ────────────────────────────────────────────────────
with tab2:
    tool_header(
        "Bulk Update Action Status",
        "Update the status of actions in bulk. Each row in your CSV maps an action to a new status.",
        requires_csv=True,
        csv_columns=["action_id", "status_id"],
    )

    st.markdown("**Valid status IDs:**")
    for sid, name in ACTION_STATUSES.items():
        st.code(f"{name}: {sid}", language=None)

    df_status = file_uploader(
        "Upload CSV with action_id and status_id",
        required_columns=["action_id", "status_id"],
        key="update_status_csv",
    )

    if df_status is not None and st.button("Update Statuses", key="run_update_status"):
        records = df_status.to_dict("records")
        token = get_token()
        progress = st.progress(0, text="Updating...")
        results_container = st.empty()

        async def _update_statuses():
            session, _ = create_async_session(token, concurrency=50)
            semaphore = asyncio.Semaphore(100)
            results = []
            completed = 0
            total = len(records)

            async def update_one(rec):
                nonlocal completed
                action_id = str(rec["action_id"]).strip()
                status_id = str(rec["status_id"]).strip()
                url = f"{BASE_URL}/tasks/v1/actions/{action_id}/status"
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                async with semaphore:
                    for attempt in range(3):
                        try:
                            async with session.put(url, json={"status_id": status_id}) as resp:
                                if resp.status == 200:
                                    completed += 1
                                    progress.progress(completed / total)
                                    return {"action_id": action_id, "status": "SUCCESS", "error": "", "timestamp": ts}
                                if resp.status in {429, 500, 502, 503, 504} and attempt < 2:
                                    await asyncio.sleep(2 ** (attempt + 1))
                                    continue
                                text = await resp.text()
                                completed += 1
                                progress.progress(completed / total)
                                return {"action_id": action_id, "status": "ERROR", "error": f"HTTP {resp.status}: {text[:200]}", "timestamp": ts}
                        except Exception as e:
                            if attempt < 2:
                                await asyncio.sleep(2 ** (attempt + 1))
                                continue
                            completed += 1
                            progress.progress(completed / total)
                            return {"action_id": action_id, "status": "ERROR", "error": str(e), "timestamp": ts}
                completed += 1
                progress.progress(completed / total)
                return {"action_id": action_id, "status": "ERROR", "error": "Max retries", "timestamp": ts}

            try:
                tasks = [update_one(r) for r in records]
                results = await asyncio.gather(*tasks)
            finally:
                await session.close()
            return results

        results = run_async(_update_statuses())
        progress.empty()
        display_results(results, "action_status_update_results.csv")


# ─── Delete Actions ──────────────────────────────────────────────────────────
with tab3:
    tool_header(
        "Bulk Delete Actions",
        "Permanently delete actions in bulk. Actions are deleted in chunks of 300. "
        "**This operation cannot be undone.**",
        requires_csv=True,
        csv_columns=["id"],
    )

    df_delete = file_uploader(
        "Upload CSV with action IDs",
        required_columns=["id"],
        key="delete_actions_csv",
    )

    if df_delete is not None:
        confirmed = confirm_destructive(
            f"You are about to **permanently delete {len(df_delete):,} actions**. This cannot be undone.",
            "delete_actions",
        )

        if confirmed and st.button("Delete Actions", key="run_delete_actions", type="primary"):
            token = get_token()
            action_ids = [str(r).strip() for r in df_delete["id"].tolist()]
            chunks = [action_ids[i:i + 300] for i in range(0, len(action_ids), 300)]
            progress = st.progress(0, text="Deleting...")
            results = []

            for i, chunk in enumerate(chunks):
                resp = __import__("requests").post(
                    f"{BASE_URL}/tasks/v1/actions/delete",
                    json={"ids": chunk},
                    headers=get_headers(token),
                    timeout=30,
                )
                success = resp.status_code == 200
                results.append({
                    "chunk": i + 1,
                    "chunk_size": len(chunk),
                    "status": "SUCCESS" if success else "ERROR",
                    "status_code": resp.status_code,
                    "error": "" if success else resp.text[:200],
                })
                progress.progress((i + 1) / len(chunks))

            progress.empty()
            display_results(results, "action_deletion_log.csv")


# ─── Delete Action Schedules ─────────────────────────────────────────────────
with tab4:
    tool_header(
        "Delete Action Schedules",
        "Remove recurring schedules from actions. You can provide a CSV with "
        "`action_id` and `schedule_id` pairs, or provide just `audit_id` values "
        "and the tool will find schedules via the API.",
        requires_csv=True,
        csv_columns=["action_id", "schedule_id"],
    )

    df_sched = file_uploader(
        "Upload CSV with action_id and schedule_id",
        required_columns=["action_id", "schedule_id"],
        key="delete_schedules_csv",
    )

    if df_sched is not None and st.button("Delete Schedules", key="run_delete_schedules"):
        token = get_token()
        pairs = [
            (str(r["action_id"]).strip(), str(r["schedule_id"]).strip())
            for _, r in df_sched.iterrows()
            if str(r["action_id"]).strip() and str(r["schedule_id"]).strip()
        ]
        progress = st.progress(0, text="Deleting schedules...")

        async def _delete_schedules():
            session, _ = create_async_session(token, concurrency=12)
            semaphore = asyncio.Semaphore(12)
            results = []
            completed = 0
            total = len(pairs)

            async def delete_one(action_id, schedule_id):
                nonlocal completed
                url = f"{BASE_URL}/tasks/v1/actions:DeleteActionSchedule"
                payload = {"schedule_id": schedule_id, "action_id": action_id}
                async with semaphore:
                    for attempt in range(3):
                        try:
                            async with session.post(url, json=payload) as resp:
                                text = await resp.text()
                                completed += 1
                                progress.progress(completed / total)
                                if resp.status in (200, 204):
                                    return {"action_id": action_id, "schedule_id": schedule_id, "status": "SUCCESS", "error": ""}
                                if resp.status in {429, 500, 502, 503, 504} and attempt < 2:
                                    await asyncio.sleep(2 ** (attempt + 1))
                                    completed -= 1
                                    continue
                                return {"action_id": action_id, "schedule_id": schedule_id, "status": "ERROR", "error": text[:200]}
                        except Exception as e:
                            if attempt < 2:
                                await asyncio.sleep(2 ** (attempt + 1))
                                continue
                            completed += 1
                            progress.progress(completed / total)
                            return {"action_id": action_id, "schedule_id": schedule_id, "status": "ERROR", "error": str(e)}
                return {"action_id": action_id, "schedule_id": schedule_id, "status": "ERROR", "error": "Max retries"}

            try:
                tasks = [delete_one(aid, sid) for aid, sid in pairs]
                results = await asyncio.gather(*tasks)
            finally:
                await session.close()
            return results

        results = run_async(_delete_schedules())
        progress.empty()
        display_results(results, "delete_schedules_log.csv")


# ─── Stop Action Recurrence ──────────────────────────────────────────────────
with tab5:
    tool_header(
        "Stop Action Recurrence",
        "Remove recurring schedules from actions without deleting the actions themselves. "
        "Provide a CSV with `action_id` and `schedule_id` pairs.",
        requires_csv=True,
        csv_columns=["action_id", "schedule_id"],
    )

    df_recur = file_uploader(
        "Upload CSV with action_id and schedule_id",
        required_columns=["action_id", "schedule_id"],
        key="stop_recurrence_csv",
    )

    if df_recur is not None and st.button("Stop Recurrence", key="run_stop_recurrence"):
        token = get_token()
        pairs = [
            (str(r["action_id"]).strip(), str(r["schedule_id"]).strip())
            for _, r in df_recur.iterrows()
            if str(r["action_id"]).strip() and str(r["schedule_id"]).strip()
        ]
        progress = st.progress(0, text="Stopping recurrence...")

        async def _stop_recurrence():
            session, _ = create_async_session(token, concurrency=12)
            semaphore = asyncio.Semaphore(12)
            results = []
            completed = 0
            total = len(pairs)

            async def stop_one(action_id, schedule_id):
                nonlocal completed
                url = f"{BASE_URL}/tasks/v1/actions:DeleteActionSchedule"
                payload = {"schedule_id": schedule_id, "action_id": action_id}
                async with semaphore:
                    for attempt in range(3):
                        try:
                            async with session.post(url, json=payload) as resp:
                                text = await resp.text()
                                completed += 1
                                progress.progress(completed / total)
                                if resp.status in (200, 204):
                                    return {"action_id": action_id, "schedule_id": schedule_id, "status": "SUCCESS", "error": ""}
                                if resp.status in {429, 500, 502, 503, 504} and attempt < 2:
                                    await asyncio.sleep(2 ** (attempt + 1))
                                    completed -= 1
                                    continue
                                return {"action_id": action_id, "schedule_id": schedule_id, "status": "ERROR", "error": text[:200]}
                        except Exception as e:
                            if attempt < 2:
                                await asyncio.sleep(2 ** (attempt + 1))
                                continue
                            completed += 1
                            progress.progress(completed / total)
                            return {"action_id": action_id, "schedule_id": schedule_id, "status": "ERROR", "error": str(e)}
                return {"action_id": action_id, "schedule_id": schedule_id, "status": "ERROR", "error": "Max retries"}

            try:
                tasks = [stop_one(aid, sid) for aid, sid in pairs]
                results = await asyncio.gather(*tasks)
            finally:
                await session.close()
            return results

        results = run_async(_stop_recurrence())
        progress.empty()
        display_results(results, "stop_recurrence_log.csv")
