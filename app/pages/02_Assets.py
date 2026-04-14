"""Assets tools - export, update, delete assets and asset types."""

import asyncio
import csv
import io
import json
import re
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
    sync_paginate_post,
)
from core.ui import (
    check_token,
    confirm_destructive,
    display_dataframe_results,
    display_results,
    file_uploader,
    tool_header,
)

st.header("Assets")
if not check_token():
    st.stop()

tab1, tab2, tab3, tab4 = st.tabs(
    ["Export Assets", "Export Asset Types", "Update Assets", "Delete Assets"]
)

# ─── Export Assets ───────────────────────────────────────────────────────────
with tab1:
    tool_header(
        "Export All Assets",
        "Exports every asset in your organization via the data feed endpoint. "
        "Custom fields are automatically flattened into separate columns.",
    )

    if st.button("Export Assets", key="export_assets"):
        token = get_token()
        progress = st.progress(0, text="Fetching assets...")

        async def _export_assets():
            session, _ = create_async_session(token)
            url = f"{BASE_URL}/feed/assets"
            all_data = []
            page_count = 0

            try:
                while url:
                    async with session.get(url) as resp:
                        resp.raise_for_status()
                        body = await resp.json()

                    data = body.get("data", [])
                    all_data.extend(data)
                    page_count += 1

                    metadata = body.get("metadata", {})
                    remaining = metadata.get("remaining_records", 0)
                    total_est = len(all_data) + remaining
                    pct = len(all_data) / total_est if total_est > 0 else 0
                    progress.progress(min(pct, 0.99), text=f"Fetched {len(all_data):,} assets ({remaining:,} remaining)...")

                    next_url = metadata.get("next_page")
                    if next_url:
                        url = next_url if next_url.startswith("http") else f"{BASE_URL}{next_url}"
                    else:
                        url = None
            finally:
                await session.close()
            return all_data

        raw = run_async(_export_assets())
        progress.progress(1.0, text="Processing...")

        if not raw:
            st.info("No assets found.")
        else:
            df = pd.json_normalize(raw, sep="_")
            progress.empty()
            display_dataframe_results(df, "assets_export.csv", f"Exported {len(df):,} Assets")


# ─── Export Asset Types ──────────────────────────────────────────────────────
with tab2:
    tool_header(
        "Export Asset Types",
        "Export all asset type definitions from your organization.",
    )

    if st.button("Export Asset Types", key="export_asset_types"):
        token = get_token()
        with st.spinner("Fetching asset types..."):
            types = sync_paginate_post(
                "/assets/v1/types/list",
                token=token,
                data_key="type_list",
                page_size=100,
            )

        if not types:
            st.info("No asset types found.")
        else:
            rows = [{"id": t.get("id", ""), "name": t.get("name", ""), "type": t.get("type", "")} for t in types]
            df = pd.DataFrame(rows)
            display_dataframe_results(df, "asset_types.csv", f"Exported {len(df):,} Asset Types")


# ─── Update Assets ───────────────────────────────────────────────────────────
with tab3:
    tool_header(
        "Bulk Update Assets",
        "Update assets from a CSV. The tool automatically maps CSV columns to asset fields. "
        "Standard fields: `code`, `site_id`. Custom fields are matched by name.",
        requires_csv=True,
        csv_columns=["id (or 'asset id' or 'internal id')"],
    )

    df_update = file_uploader(
        "Upload CSV with asset data to update",
        key="update_assets_csv",
    )

    if df_update is not None and st.button("Update Assets", key="run_update_assets"):
        token = get_token()
        progress = st.progress(0, text="Fetching field definitions...")

        # Fetch field definitions
        resp = requests.post(
            f"{BASE_URL}/assets/v1/fields/list",
            headers=get_headers(token),
            json={},
            timeout=30,
        )
        resp.raise_for_status()
        fields = resp.json().get("result", [])

        # Find ID column
        id_col = None
        for col in df_update.columns:
            if col.lower().replace(" ", "").replace("_", "") in ["id", "assetid", "internalid"]:
                id_col = col
                break
        if not id_col:
            st.error("No ID column found. Add a column named 'id', 'asset id', or 'internal id'.")
            st.stop()

        # Find code and site columns
        code_col = None
        site_col = None
        for col in df_update.columns:
            norm = col.lower().replace(" ", "").replace("_", "")
            if norm in ["code", "uniqueid", "assetcode", "uniquecode"]:
                code_col = col
            if norm in ["siteid", "site"]:
                site_col = col

        # Build field lookup
        field_by_name = {}
        for f in fields:
            field_by_name[f.get("name", "").lower().strip()] = f

        # Map CSV columns to fields
        field_map = {}
        for col in df_update.columns:
            if col in [id_col, code_col, site_col]:
                continue
            match = field_by_name.get(col.lower().strip())
            if match:
                field_map[col] = match

        st.info(f"Mapped {len(field_map)} custom fields, code={'yes' if code_col else 'no'}, site={'yes' if site_col else 'no'}")

        # Build payloads and update
        records = df_update.to_dict("records")
        assets = []
        mask_parts = set()

        for row in records:
            asset_id = str(row.get(id_col, "")).strip()
            if not asset_id:
                continue
            asset = {"id": asset_id}
            if code_col and str(row.get(code_col, "")).strip():
                asset["code"] = str(row[code_col]).strip()
                mask_parts.add("code")
            if site_col and str(row.get(site_col, "")).strip():
                asset["site"] = {"id": str(row[site_col]).strip()}
                mask_parts.add("site")
            asset_fields = []
            for col, field_def in field_map.items():
                val = str(row.get(col, "")).strip()
                if val:
                    asset_fields.append({"field_id": field_def["id"], "string_value": val})
            if asset_fields:
                asset["fields"] = asset_fields
                mask_parts.add("fields")
            if len(asset) > 1:
                assets.append(asset)

        if not assets:
            st.warning("No valid assets to update.")
        else:
            update_mask = ",".join(mask_parts)
            chunk_size = 100
            chunks = [assets[i:i + chunk_size] for i in range(0, len(assets), chunk_size)]
            results = []

            for i, chunk in enumerate(chunks):
                resp = requests.put(
                    f"{BASE_URL}/assets/v1/assets/bulk",
                    headers=get_headers(token),
                    json={"assets": chunk, "update_mask": update_mask},
                    timeout=60,
                )
                success = resp.status_code in (200, 201)
                if success:
                    data = resp.json()
                    for a in data.get("updated_assets", []):
                        results.append({"asset_id": a.get("id", ""), "status": "SUCCESS", "error": ""})
                    for a in data.get("failed_assets", []):
                        err = a.get("error", {}).get("message", str(a.get("error", "")))
                        results.append({"asset_id": a.get("id", ""), "status": "ERROR", "error": err})
                else:
                    for a in chunk:
                        results.append({"asset_id": a.get("id", ""), "status": "ERROR", "error": f"HTTP {resp.status_code}"})
                progress.progress((i + 1) / len(chunks))

            progress.empty()
            display_results(results, "asset_update_results.csv")


# ─── Delete Assets ───────────────────────────────────────────────────────────
with tab4:
    tool_header(
        "Delete Assets",
        "Archive and then permanently delete assets. Assets are first archived, then deleted. "
        "**This operation cannot be undone.**",
        requires_csv=True,
        csv_columns=["id (or 'asset_id' or 'uuid')"],
    )

    df_del = file_uploader(
        "Upload CSV with asset IDs",
        key="delete_assets_csv",
    )

    if df_del is not None:
        # Find ID column
        id_col = None
        for col in df_del.columns:
            if col.lower() in ["asset_id", "id", "uuid"]:
                id_col = col
                break
        if not id_col:
            st.error("CSV must include a column named 'asset_id', 'id', or 'uuid'.")
        else:
            confirmed = confirm_destructive(
                f"You are about to **permanently delete {len(df_del):,} assets**. This cannot be undone.",
                "delete_assets",
            )
            if confirmed and st.button("Delete Assets", key="run_delete_assets", type="primary"):
                token = get_token()
                asset_ids = [str(r).strip() for r in df_del[id_col].tolist() if str(r).strip()]
                progress = st.progress(0, text="Deleting assets...")

                async def _delete_assets():
                    session, _ = create_async_session(token, concurrency=12)
                    semaphore = asyncio.Semaphore(12)
                    results = []
                    completed = 0
                    total = len(asset_ids)

                    async def delete_one(asset_id):
                        nonlocal completed
                        # Archive first
                        async with semaphore:
                            try:
                                async with session.patch(
                                    f"{BASE_URL}/assets/v1/assets/{asset_id}/archive", json={}
                                ) as resp:
                                    pass  # Best effort archive
                            except Exception:
                                pass
                            # Then delete
                            for attempt in range(3):
                                try:
                                    async with session.delete(f"{BASE_URL}/assets/v1/assets/{asset_id}") as resp:
                                        completed += 1
                                        progress.progress(completed / total)
                                        if resp.status in (200, 204):
                                            return {"asset_id": asset_id, "status": "SUCCESS", "error": ""}
                                        if resp.status in {429, 500, 502, 503, 504} and attempt < 2:
                                            await asyncio.sleep(2 ** (attempt + 1))
                                            completed -= 1
                                            continue
                                        text = await resp.text()
                                        return {"asset_id": asset_id, "status": "ERROR", "error": text[:200]}
                                except Exception as e:
                                    if attempt < 2:
                                        await asyncio.sleep(2 ** (attempt + 1))
                                        continue
                                    completed += 1
                                    progress.progress(completed / total)
                                    return {"asset_id": asset_id, "status": "ERROR", "error": str(e)}
                        return {"asset_id": asset_id, "status": "ERROR", "error": "Max retries"}

                    try:
                        tasks = [delete_one(aid) for aid in asset_ids]
                        results = await asyncio.gather(*tasks)
                    finally:
                        await session.close()
                    return results

                results = run_async(_delete_assets())
                progress.empty()
                display_results(results, "delete_assets_log.csv")
