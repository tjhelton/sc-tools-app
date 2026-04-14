"""Schedules tools - export and update schedule items."""

import asyncio
import json

import pandas as pd
import requests
import streamlit as st

from core.api import BASE_URL, create_async_session, get_headers, get_token, run_async
from core.ui import (
    check_token,
    display_dataframe_results,
    display_results,
    tool_header,
)

st.header("Schedules")
if not check_token():
    st.stop()

tab1, tab2 = st.tabs(["Export Schedules", "Update Schedules"])

READ_ONLY_COLS = {
    "id", "status", "creator_name", "created_at", "modified_at",
    "next_occurrence_start", "next_occurrence_due",
}


def flatten_schedule(item):
    """Flatten a schedule item into a flat dict for CSV export."""
    start_time = item.get("start_time") or {}
    document = item.get("document") or {}
    creator = item.get("creator") or {}
    next_occ = item.get("next_occurrence") or {}

    return {
        "id": item.get("id", ""),
        "status": item.get("status", ""),
        "description": item.get("description", ""),
        "recurrence": item.get("recurrence", ""),
        "start_time_hour": start_time.get("hour", ""),
        "start_time_minute": start_time.get("minute", ""),
        "duration": item.get("duration", ""),
        "timezone": item.get("timezone", ""),
        "from_date": item.get("from_date", ""),
        "to_date": item.get("to_date", ""),
        "can_late_submit": item.get("can_late_submit", ""),
        "must_complete": item.get("must_complete", ""),
        "site_based_assignment_enabled": item.get("site_based_assignment_enabled", ""),
        "location_id": item.get("location_id", ""),
        "asset_id": item.get("asset_id", ""),
        "document_id": document.get("id", ""),
        "document_type": document.get("type", ""),
        "creator_name": creator.get("name", ""),
        "created_at": item.get("created_at", ""),
        "modified_at": item.get("modified_at", ""),
        "next_occurrence_start": next_occ.get("start", ""),
        "next_occurrence_due": next_occ.get("due", ""),
        "assignees": json.dumps(item.get("assignees", [])),
        "reminders": json.dumps(item.get("reminders", [])),
    }


def fetch_schedules(token, statuses, progress=None):
    """Fetch schedule items with optional status filter."""
    headers = get_headers(token)
    all_items = []
    page_token = None
    page = 0

    while True:
        params = {"page_size": 100}
        if page_token:
            params["page_token"] = page_token
        if statuses:
            params["status"] = statuses

        resp = requests.get(
            f"{BASE_URL}/schedules/v1/schedule_items",
            headers=headers,
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()

        items = body.get("items", [])
        all_items.extend(items)
        page += 1

        total = body.get("total", len(all_items))
        if progress and total > 0:
            progress.progress(
                min(0.95, len(all_items) / total),
                text=f"Fetched {len(all_items):,} of {total:,} schedules...",
            )

        page_token = body.get("next_page_token")
        if not page_token:
            break

    return all_items


# ─── Export Schedules ───────────────────────────────────────────────────────
with tab1:
    tool_header(
        "Export Schedules",
        "Export all schedule items with optional status filtering. "
        "Results include recurrence rules, assignees, and timing details.",
    )

    status_filter = st.multiselect(
        "Filter by status (leave empty for all)",
        ["ACTIVE", "PAUSED", "ARCHIVED"],
        key="schedule_status_filter",
    )

    if st.button("Export Schedules", key="run_export_schedules"):
        token = get_token()
        progress = st.progress(0, text="Fetching schedules...")

        try:
            statuses = status_filter if status_filter else None
            raw_items = fetch_schedules(token, statuses, progress)
        except Exception as e:
            st.error(f"API error: {e}")
            raw_items = []
        finally:
            progress.empty()

        if raw_items:
            rows = [flatten_schedule(item) for item in raw_items]
            df = pd.DataFrame(rows)
            display_dataframe_results(df, "schedules.csv", f"Exported {len(df):,} Schedules")
        else:
            st.info("No schedules found.")


# ─── Update Schedules ──────────────────────────────────────────────────────
with tab2:
    tool_header(
        "Update Schedules",
        "Three-step workflow: **1)** Export current schedules to CSV, "
        "**2)** Edit the CSV offline (change any editable columns), "
        "**3)** Upload the edited CSV to apply changes. "
        "Read-only columns (id, status, creator_name, created_at, modified_at, "
        "next_occurrence_start, next_occurrence_due) are ignored during updates.",
    )

    st.markdown("#### Step 1 — Export current schedules")
    update_status_filter = st.multiselect(
        "Filter by status",
        ["ACTIVE", "PAUSED", "ARCHIVED"],
        default=["ACTIVE"],
        key="update_schedule_status_filter",
    )

    if st.button("Export for Editing", key="run_export_for_edit"):
        token = get_token()
        progress = st.progress(0, text="Fetching schedules...")
        try:
            statuses = update_status_filter if update_status_filter else None
            raw_items = fetch_schedules(token, statuses, progress)
        except Exception as e:
            st.error(f"API error: {e}")
            raw_items = []
        finally:
            progress.empty()

        if raw_items:
            rows = [flatten_schedule(item) for item in raw_items]
            df = pd.DataFrame(rows)
            st.session_state["schedule_snapshot"] = df.copy()
            st.success(f"Exported {len(df):,} schedules. Download, edit, then re-upload below.")

            csv_bytes = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download schedules CSV",
                csv_bytes,
                file_name="schedules_for_editing.csv",
                mime="text/csv",
                key="download_schedules_edit",
            )
        else:
            st.info("No schedules found.")

    st.divider()
    st.markdown("#### Step 2 — Upload edited CSV")

    uploaded = st.file_uploader(
        "Upload edited schedules CSV",
        type=["csv"],
        key="upload_edited_schedules",
        help="Must contain an 'id' column. Only changed editable columns are sent.",
    )

    if uploaded is not None:
        try:
            edited_df = pd.read_csv(uploaded).fillna("")
        except Exception as e:
            st.error(f"Error reading CSV: {e}")
            edited_df = None

        if edited_df is not None and "id" not in edited_df.columns:
            st.error("The uploaded CSV must contain an 'id' column.")
            edited_df = None

        if edited_df is not None:
            snapshot = st.session_state.get("schedule_snapshot")

            # Detect changes
            changes = []
            if snapshot is not None:
                snapshot_idx = snapshot.set_index("id")
                for _, row in edited_df.iterrows():
                    sid = str(row["id"]).strip()
                    if sid not in snapshot_idx.index:
                        continue
                    orig = snapshot_idx.loc[sid]
                    diff = {}
                    for col in edited_df.columns:
                        if col in READ_ONLY_COLS:
                            continue
                        new_val = str(row[col]).strip()
                        old_val = str(orig.get(col, "")).strip()
                        if new_val != old_val:
                            diff[col] = new_val
                    if diff:
                        changes.append({"id": sid, **diff})
            else:
                # No snapshot — treat all editable columns as the update payload
                for _, row in edited_df.iterrows():
                    sid = str(row["id"]).strip()
                    payload = {}
                    for col in edited_df.columns:
                        if col in READ_ONLY_COLS:
                            continue
                        val = str(row[col]).strip()
                        if val:
                            payload[col] = val
                    if payload:
                        changes.append({"id": sid, **payload})

            if not changes:
                st.info("No changes detected between the original and edited CSV.")
            else:
                st.success(f"Detected changes in {len(changes):,} schedule(s).")
                with st.expander("Preview changes"):
                    st.dataframe(pd.DataFrame(changes).head(50), use_container_width=True)

                if st.button("Apply Updates", key="run_apply_schedule_updates"):
                    token = get_token()
                    progress = st.progress(0, text="Updating schedules...")

                    async def _apply_updates():
                        session, _ = create_async_session(token, concurrency=20)
                        semaphore = asyncio.Semaphore(20)
                        completed = 0
                        total = len(changes)
                        results = []

                        async def update_one(change):
                            nonlocal completed
                            sid = change.pop("id")
                            # Build payload with proper nesting
                            payload = {}
                            for k, v in change.items():
                                if k == "start_time_hour" or k == "start_time_minute":
                                    if "start_time" not in payload:
                                        payload["start_time"] = {}
                                    field = k.replace("start_time_", "")
                                    try:
                                        payload["start_time"][field] = int(v)
                                    except (ValueError, TypeError):
                                        payload["start_time"][field] = v
                                elif k == "document_id" or k == "document_type":
                                    if "document" not in payload:
                                        payload["document"] = {}
                                    field = k.replace("document_", "")
                                    payload["document"][field] = v
                                elif k in ("assignees", "reminders"):
                                    try:
                                        payload[k] = json.loads(v)
                                    except (json.JSONDecodeError, TypeError):
                                        payload[k] = v
                                elif k in ("can_late_submit", "site_based_assignment_enabled"):
                                    payload[k] = v.lower() in ("true", "1", "yes")
                                else:
                                    payload[k] = v

                            async with semaphore:
                                try:
                                    async with session.put(
                                        f"{BASE_URL}/schedules/v1/schedule_items/{sid}",
                                        json=payload,
                                    ) as resp:
                                        completed += 1
                                        progress.progress(completed / total)
                                        if resp.status == 200:
                                            return {"schedule_id": sid, "status": "SUCCESS", "error": ""}
                                        text = await resp.text()
                                        return {
                                            "schedule_id": sid,
                                            "status": "ERROR",
                                            "error": f"HTTP {resp.status}: {text[:200]}",
                                        }
                                except Exception as e:
                                    completed += 1
                                    return {"schedule_id": sid, "status": "ERROR", "error": str(e)}

                        tasks = [update_one(c) for c in changes]
                        return await asyncio.gather(*tasks)

                    try:
                        results = list(run_async(_apply_updates()))
                    finally:
                        progress.empty()

                    display_results(results, "schedule_update_results.csv")
