"""Inspections tools - archive, unarchive, delete, export PDFs, location changes, update site."""

import asyncio
import io
import time
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
    confirm_destructive,
    display_results,
    file_uploader,
    tool_header,
)

st.header("Inspections")
if not check_token():
    st.stop()

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "Archive", "Unarchive", "Delete", "Export PDFs",
    "Location Changes", "Update Site", "Complete",
])


# ─── Helper: bulk inspection operation ────────────────────────────────────────
async def _bulk_inspection_op(audit_ids, token, endpoint_fn, method, body_fn, progress, concurrency=30, rate_limit=800):
    """Generic bulk operation on inspections."""
    session, _ = create_async_session(token, concurrency=concurrency)
    semaphore = asyncio.Semaphore(concurrency)
    results = []
    completed = 0
    total = len(audit_ids)

    async def process_one(audit_id):
        nonlocal completed
        url = endpoint_fn(audit_id)
        body = body_fn(audit_id) if body_fn else {}
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        async with semaphore:
            for attempt in range(3):
                try:
                    async with session.request(method, url, json=body) as resp:
                        if resp.status == 200:
                            completed += 1
                            progress.progress(completed / total)
                            return {"audit_id": audit_id, "status": "SUCCESS", "error": "", "timestamp": ts}
                        if resp.status in {429, 500, 502, 503, 504} and attempt < 2:
                            await asyncio.sleep(2 ** (attempt + 1))
                            continue
                        text = await resp.text()
                        completed += 1
                        progress.progress(completed / total)
                        return {"audit_id": audit_id, "status": "ERROR", "error": f"HTTP {resp.status}: {text[:200]}", "timestamp": ts}
                except Exception as e:
                    if attempt < 2:
                        await asyncio.sleep(2 ** (attempt + 1))
                        continue
                    completed += 1
                    progress.progress(completed / total)
                    return {"audit_id": audit_id, "status": "ERROR", "error": str(e), "timestamp": ts}
            completed += 1
            progress.progress(completed / total)
            return {"audit_id": audit_id, "status": "ERROR", "error": "Max retries", "timestamp": ts}

    try:
        tasks = [process_one(aid) for aid in audit_ids]
        results = await asyncio.gather(*tasks)
    finally:
        await session.close()
    return list(results)


def _load_audit_ids(df):
    return [str(r).strip() for r in df["audit_id"].tolist() if str(r).strip()]


# ─── Archive Inspections ─────────────────────────────────────────────────────
with tab1:
    tool_header(
        "Bulk Archive Inspections",
        "Archive inspections in bulk with high-throughput async processing.",
        requires_csv=True, csv_columns=["audit_id"],
    )
    df = file_uploader("Upload CSV", required_columns=["audit_id"], key="archive_insp_csv")
    if df is not None and st.button("Archive Inspections", key="run_archive"):
        ids = _load_audit_ids(df)
        progress = st.progress(0, text=f"Archiving {len(ids):,} inspections...")
        results = run_async(_bulk_inspection_op(
            ids, get_token(),
            lambda aid: f"{BASE_URL}/inspections/v1/inspections/{aid}/archive",
            "POST", lambda aid: {}, progress,
        ))
        progress.empty()
        display_results(results, "archive_results.csv")


# ─── Unarchive Inspections ───────────────────────────────────────────────────
with tab2:
    tool_header(
        "Bulk Unarchive Inspections",
        "Restore archived inspections in bulk.",
        requires_csv=True, csv_columns=["audit_id"],
    )
    df = file_uploader("Upload CSV", required_columns=["audit_id"], key="unarchive_insp_csv")
    if df is not None and st.button("Unarchive Inspections", key="run_unarchive"):
        ids = _load_audit_ids(df)
        progress = st.progress(0, text=f"Unarchiving {len(ids):,} inspections...")
        results = run_async(_bulk_inspection_op(
            ids, get_token(),
            lambda aid: f"{BASE_URL}/audits/{aid}",
            "PUT", lambda aid: {"archived": False}, progress,
        ))
        progress.empty()
        display_results(results, "unarchive_results.csv")


# ─── Delete Inspections ──────────────────────────────────────────────────────
with tab3:
    tool_header(
        "Bulk Delete Inspections",
        "**Permanently** delete inspections. **This cannot be undone.**",
        requires_csv=True, csv_columns=["audit_id"],
    )
    df = file_uploader("Upload CSV", required_columns=["audit_id"], key="delete_insp_csv")
    if df is not None:
        confirmed = confirm_destructive(
            f"You are about to **permanently delete {len(df):,} inspections**.",
            "delete_inspections",
        )
        if confirmed and st.button("Delete Inspections", key="run_delete_insp", type="primary"):
            ids = _load_audit_ids(df)
            progress = st.progress(0, text=f"Deleting {len(ids):,} inspections...")
            results = run_async(_bulk_inspection_op(
                ids, get_token(),
                lambda aid: f"{BASE_URL}/inspections/v1/inspections/{aid}",
                "DELETE", None, progress, concurrency=12,
            ))
            progress.empty()
            display_results(results, "delete_inspections_results.csv")


# ─── Export PDFs ─────────────────────────────────────────────────────────────
with tab4:
    tool_header(
        "Export Inspection PDFs",
        "Generate and download PDF exports for inspections. PDFs are generated server-side "
        "and downloaded when ready. Note: PDF files are downloaded to a temporary directory.",
        requires_csv=True, csv_columns=["audit_id", "audit_title", "template_name"],
    )
    st.info("Due to browser limitations, this tool exports the PDF metadata and download URLs. "
            "For bulk file downloads, use the original script.")

    df = file_uploader("Upload CSV", required_columns=["audit_id"], key="export_pdfs_csv")
    if df is not None and st.button("Export PDF Links", key="run_export_pdfs"):
        token = get_token()
        records = df.to_dict("records")
        progress = st.progress(0, text="Requesting PDF exports...")

        async def _export_pdfs():
            session, _ = create_async_session(token, concurrency=12)
            semaphore = asyncio.Semaphore(12)
            results = []
            completed = 0
            total = len(records)

            async def export_one(row):
                nonlocal completed
                audit_id = str(row.get("audit_id", "")).strip()
                title = str(row.get("audit_title", "Unknown")).strip()
                template = str(row.get("template_name", "Unknown")).strip()
                url = f"{BASE_URL}/inspection/v1/export"
                body = {
                    "export_data": [{"inspection_id": audit_id, "lang": "en"}],
                    "type": "DOCUMENT_TYPE_PDF",
                    "timezone": "UTC",
                    "regenerate": False,
                }

                async with semaphore:
                    try:
                        # Submit export request
                        async with session.post(url, json=body) as resp:
                            if resp.status != 200:
                                completed += 1
                                progress.progress(completed / total)
                                return {"audit_id": audit_id, "title": title, "status": "ERROR", "url": "", "error": f"HTTP {resp.status}"}
                            data = await resp.json()

                        # Poll for completion
                        for _ in range(30):
                            if data.get("status") == "STATUS_DONE" and data.get("url"):
                                completed += 1
                                progress.progress(completed / total)
                                return {"audit_id": audit_id, "title": title, "status": "SUCCESS", "url": data["url"], "error": ""}
                            if data.get("status") == "STATUS_FAILED":
                                completed += 1
                                progress.progress(completed / total)
                                return {"audit_id": audit_id, "title": title, "status": "ERROR", "url": "", "error": "Export failed"}
                            await asyncio.sleep(2)
                            async with session.post(url, json=body) as resp:
                                if resp.status == 200:
                                    data = await resp.json()

                        completed += 1
                        progress.progress(completed / total)
                        return {"audit_id": audit_id, "title": title, "status": "ERROR", "url": "", "error": "Timeout"}
                    except Exception as e:
                        completed += 1
                        progress.progress(completed / total)
                        return {"audit_id": audit_id, "title": title, "status": "ERROR", "url": "", "error": str(e)}

            try:
                tasks = [export_one(r) for r in records]
                results = await asyncio.gather(*tasks)
            finally:
                await session.close()
            return results

        results = run_async(_export_pdfs())
        progress.empty()
        display_results(results, "pdf_export_results.csv")


# ─── Location Changes ────────────────────────────────────────────────────────
with tab5:
    tool_header(
        "Export Inspection Location Changes",
        "Export address field modifications from inspection revision history. "
        "Filters for actual location changes (excludes initial responses).",
        requires_csv=True, csv_columns=["audit_id"],
    )
    df = file_uploader("Upload CSV", required_columns=["audit_id"], key="location_changes_csv")
    if df is not None and st.button("Export Location Changes", key="run_location_changes"):
        token = get_token()
        audit_ids = _load_audit_ids(df)
        progress = st.progress(0, text="Fetching revision history...")

        async def _export_location_changes():
            session, _ = create_async_session(token, concurrency=12)
            semaphore = asyncio.Semaphore(12)
            all_changes = []
            completed = 0
            total = len(audit_ids)

            async def process_one(audit_id):
                nonlocal completed
                async with semaphore:
                    url = f"{BASE_URL}/inspections/history/{audit_id}/revisions"
                    all_results = []
                    offset = 0
                    page_size = 10

                    # Fetch first page
                    try:
                        async with session.get(url, params={"offset": 0, "limit": page_size}) as resp:
                            if resp.status != 200:
                                completed += 1
                                progress.progress(completed / total)
                                return []
                            data = await resp.json()
                            all_results = data.get("results", [])

                        # If full page, fetch more
                        if len(all_results) >= page_size:
                            for pg in range(1, 100):
                                try:
                                    async with session.get(url, params={"offset": pg * page_size, "limit": page_size}) as resp:
                                        if resp.status != 200:
                                            break
                                        data = await resp.json()
                                        page_results = data.get("results", [])
                                        if not page_results:
                                            break
                                        all_results.extend(page_results)
                                except Exception:
                                    break
                    except Exception:
                        completed += 1
                        progress.progress(completed / total)
                        return []

                    # Extract location changes
                    changes = []
                    for result in all_results:
                        for change in result.get("changes", []):
                            if change.get("field_type") != "address":
                                continue
                            old_text = change.get("old_response", {}).get("location_text", "")
                            new_text = change.get("new_response", {}).get("location_text", "")
                            if old_text == "N/A - Initial Response" or old_text == new_text:
                                continue
                            changes.append({
                                "audit_id": audit_id,
                                "user_id": result.get("author", ""),
                                "user_name": result.get("author_name", ""),
                                "old_location_text": old_text,
                                "new_location_text": new_text,
                                "timestamp": result.get("modified_at", ""),
                            })

                    completed += 1
                    progress.progress(completed / total)
                    return changes

            try:
                tasks = [process_one(aid) for aid in audit_ids]
                results = await asyncio.gather(*tasks)
                for changes in results:
                    all_changes.extend(changes)
            finally:
                await session.close()
            return all_changes

        changes = run_async(_export_location_changes())
        progress.empty()
        if changes:
            df_results = pd.DataFrame(changes)
            from core.ui import display_dataframe_results
            display_dataframe_results(df_results, "location_changes.csv", f"Found {len(changes):,} Location Changes")
        else:
            st.info("No location changes found.")


# ─── Update Inspection Site ──────────────────────────────────────────────────
with tab6:
    tool_header(
        "Update Inspection Site",
        "Assign a site to inspections in bulk.",
        requires_csv=True, csv_columns=["audit_id", "site_id"],
    )
    df = file_uploader("Upload CSV", required_columns=["audit_id", "site_id"], key="update_site_csv")
    if df is not None and st.button("Update Sites", key="run_update_site"):
        token = get_token()
        records = df.to_dict("records")
        progress = st.progress(0, text="Updating inspection sites...")
        results = []
        for i, row in enumerate(records):
            audit_id = str(row["audit_id"]).strip()
            site_id = str(row["site_id"]).strip()
            try:
                resp = requests.put(
                    f"{BASE_URL}/inspections/v1/inspections/{audit_id}/site",
                    json={"site_id": site_id},
                    headers=get_headers(token),
                    timeout=30,
                )
                resp.raise_for_status()
                results.append({"audit_id": audit_id, "site_id": site_id, "status": "SUCCESS", "error": ""})
            except Exception as e:
                results.append({"audit_id": audit_id, "site_id": site_id, "status": "ERROR", "error": str(e)})
            progress.progress((i + 1) / len(records))
        progress.empty()
        display_results(results, "update_site_results.csv")


# ─── Complete Inspections ────────────────────────────────────────────────────
with tab7:
    tool_header(
        "Complete Inspections",
        "Mark inspections as complete in bulk. Uses the private completions endpoint.",
        requires_csv=True, csv_columns=["audit_id"],
    )
    df = file_uploader("Upload CSV", required_columns=["audit_id"], key="complete_insp_csv")
    if df is not None and st.button("Complete Inspections", key="run_complete_insp"):
        ids = _load_audit_ids(df)
        progress = st.progress(0, text=f"Completing {len(ids):,} inspections...")
        results = run_async(_bulk_inspection_op(
            ids, get_token(),
            lambda aid: f"{BASE_URL}/inspections/v1/inspections/{aid}/complete",
            "POST", lambda aid: {}, progress,
        ))
        progress.empty()
        display_results(results, "complete_inspections_results.csv")
