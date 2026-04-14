"""Templates tools - archive, export access rules, export questions."""

import asyncio
import csv
import io
import json
import time
from typing import Dict, List

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
    sync_paginate_feed,
)
from core.ui import (
    check_token,
    display_dataframe_results,
    display_results,
    file_uploader,
    tool_header,
)

st.header("Templates")
if not check_token():
    st.stop()

tab1, tab2, tab3 = st.tabs(["Archive Templates", "Export Access Rules", "Export Questions"])


# ─── Archive Templates ───────────────────────────────────────────────────────
with tab1:
    tool_header(
        "Bulk Archive Templates",
        "Archive templates in bulk by providing their template IDs.",
        requires_csv=True,
        csv_columns=["template_id"],
    )

    df = file_uploader("Upload CSV", required_columns=["template_id"], key="archive_templates_csv")
    if df is not None and st.button("Archive Templates", key="run_archive_templates"):
        token = get_token()
        records = df.to_dict("records")
        progress = st.progress(0, text="Archiving templates...")
        results = []

        for i, row in enumerate(records):
            tid = str(row["template_id"]).strip()
            try:
                resp = requests.post(
                    f"{BASE_URL}/templates/v1/templates/{tid}/archive",
                    headers={"authorization": f"Bearer {token}"},
                    timeout=30,
                )
                results.append({
                    "template_id": tid,
                    "status": "SUCCESS" if resp.status_code == 200 else "ERROR",
                    "response": resp.text[:200],
                })
            except Exception as e:
                results.append({"template_id": tid, "status": "ERROR", "response": str(e)})
            progress.progress((i + 1) / len(records))

        progress.empty()
        display_results(results, "archive_templates_results.csv")


# ─── Export Access Rules ─────────────────────────────────────────────────────
with tab2:
    tool_header(
        "Export Template Access Rules",
        "Export the permission matrix for all active templates. Shows who has access "
        "to each template, including users and groups.",
    )

    if st.button("Export Access Rules", key="run_access_rules"):
        token = get_token()
        progress = st.progress(0, text="Fetching templates, users, and groups...")

        async def _export_access_rules():
            session, _ = create_async_session(token, concurrency=30)
            headers = get_headers(token)

            try:
                # Fetch users
                progress.progress(0.05, text="Fetching users...")
                users_data = []
                url = f"{BASE_URL}/feed/users"
                while url:
                    async with session.get(url) as resp:
                        resp.raise_for_status()
                        body = await resp.json()
                    users_data.extend(body.get("data", []))
                    np = body.get("metadata", {}).get("next_page")
                    url = (np if np.startswith("http") else f"{BASE_URL}{np}") if np else None

                def transform_id(feed_id):
                    if "_" not in feed_id:
                        return feed_id
                    uuid_part = feed_id.split("_")[1]
                    if len(uuid_part) == 32:
                        return f"{uuid_part[:8]}-{uuid_part[8:12]}-{uuid_part[12:16]}-{uuid_part[16:20]}-{uuid_part[20:]}"
                    return uuid_part

                users_lookup = {}
                for u in users_data:
                    uid = u.get("id", "")
                    name = f"{u.get('firstname', '')} {u.get('lastname', '')}".strip() or u.get("email", "Unknown")
                    users_lookup[transform_id(uid)] = name

                # Fetch groups
                progress.progress(0.15, text="Fetching groups...")
                groups_data = []
                url = f"{BASE_URL}/feed/groups"
                while url:
                    async with session.get(url) as resp:
                        resp.raise_for_status()
                        body = await resp.json()
                    groups_data.extend(body.get("data", []))
                    np = body.get("metadata", {}).get("next_page")
                    url = (np if np.startswith("http") else f"{BASE_URL}{np}") if np else None

                groups_lookup = {transform_id(g.get("id", "")): g.get("name", "Unknown") for g in groups_data}

                # Fetch template list
                progress.progress(0.25, text="Fetching template list...")
                templates_data = []
                url = f"{BASE_URL}/feed/templates"
                while url:
                    async with session.get(url) as resp:
                        resp.raise_for_status()
                        body = await resp.json()
                    templates_data.extend(body.get("data", []))
                    np = body.get("metadata", {}).get("next_page")
                    url = (np if np.startswith("http") else f"{BASE_URL}{np}") if np else None

                active = [t for t in templates_data if not t.get("archived", False)]
                template_ids = [t.get("id") for t in active]
                template_summaries = {t.get("id"): t for t in active}
                for t in active:
                    template_summaries[transform_id(t.get("id", ""))] = t

                # Fetch template details
                progress.progress(0.4, text=f"Fetching {len(template_ids)} template details...")
                semaphore = asyncio.Semaphore(10)
                completed = 0

                async def fetch_template(tid):
                    nonlocal completed
                    async with semaphore:
                        await asyncio.sleep(0.1)
                        try:
                            async with session.get(f"{BASE_URL}/templates/v1/templates/{tid}") as resp:
                                completed += 1
                                pct = 0.4 + (completed / len(template_ids) * 0.5)
                                progress.progress(min(pct, 0.95), text=f"Fetching template {completed}/{len(template_ids)}...")
                                if resp.status == 200:
                                    data = await resp.json()
                                    return data.get("template")
                                return None
                        except Exception:
                            completed += 1
                            return None

                tasks = [fetch_template(tid) for tid in template_ids]
                template_details = await asyncio.gather(*tasks)

                # Process permissions
                progress.progress(0.95, text="Processing permissions...")
                records = []
                for template in template_details:
                    if not template:
                        continue
                    tid = template.get("id", "")
                    tname = template.get("name", "")
                    summary = template_summaries.get(tid, {})
                    owner = summary.get("owner_name", "Unknown")

                    for perm_type, perm_list in template.get("permissions", {}).items():
                        if not isinstance(perm_list, list):
                            continue
                        for entry in perm_list:
                            assignee_id = entry.get("id", "")
                            if entry.get("type") == "ROLE":
                                assignee_type = "group"
                                assignee_name = groups_lookup.get(assignee_id, f"Unknown ({assignee_id})")
                            else:
                                assignee_type = "user"
                                assignee_name = users_lookup.get(assignee_id, f"Unknown ({assignee_id})")
                            records.append({
                                "template_id": tid,
                                "name": tname,
                                "template_owner": owner,
                                "permission": perm_type,
                                "assignee_type": assignee_type,
                                "assignee_id": assignee_id,
                                "assignee_name": assignee_name,
                            })

                return records
            finally:
                await session.close()

        records = run_async(_export_access_rules())
        progress.empty()

        if records:
            df = pd.DataFrame(records)
            display_dataframe_results(df, "template_access_rules.csv", f"Exported {len(records):,} Access Rules")
        else:
            st.info("No access rules found.")


# ─── Export Template Questions ────────────────────────────────────────────────
with tab3:
    tool_header(
        "Export Template Questions",
        "Recursively extract all questions from templates, including response options, "
        "page/section hierarchy, and item types.",
    )

    mode = st.radio("Mode", ["Export all templates", "Specific template IDs"], key="tq_mode")
    template_ids_input = ""
    if mode == "Specific template IDs":
        template_ids_input = st.text_area(
            "Template IDs (one per line or comma-separated)", key="tq_ids"
        )

    if st.button("Export Questions", key="run_export_questions"):
        token = get_token()
        progress = st.progress(0, text="Preparing...")

        def extract_questions(items, response_sets=None, page_id=None, page_label=None,
                              section_id=None, section_label=None, template_id="", template_name=""):
            if response_sets is None:
                response_sets = {}
            questions = []
            for item in items:
                item_id = item.get("id", "")
                item_label = item.get("label", "")
                children = item.get("children", [])
                item_type = None
                for key in item.keys():
                    if key not in ["id", "label", "children"]:
                        item_type = key
                        break

                if item_type == "logicfield":
                    questions.extend(extract_questions(children, response_sets, page_id, page_label,
                                                       section_id, section_label, template_id, template_name))
                    continue

                possible_responses = ""
                if item_type and item_type in item:
                    td = item[item_type]
                    if isinstance(td, dict):
                        rsid = td.get("response_set_id")
                        if rsid and rsid in response_sets:
                            resps = response_sets[rsid].get("responses", [])
                            possible_responses = "; ".join(r.get("label", "") for r in resps if isinstance(r, dict))
                        elif "responses" in td:
                            resps = td.get("responses", [])
                            possible_responses = "; ".join(r.get("label", "") for r in resps if isinstance(r, dict))

                if item_type and item_type not in ["section", "category"]:
                    questions.append({
                        "item_id": item_id, "item_label": item_label,
                        "possible_responses": possible_responses, "item_type": item_type,
                        "page_id": page_id or "", "page_label": page_label or "",
                        "section_id": section_id or "", "section_label": section_label or "",
                        "template_id": template_id, "template_name": template_name,
                    })

                if children:
                    if item_type == "section":
                        cpid, cpl, csid, csl = item_id, item_label, None, None
                    elif item_type == "category":
                        cpid, cpl, csid, csl = page_id, page_label, item_id, item_label
                    else:
                        cpid, cpl, csid, csl = page_id, page_label, section_id, section_label
                    questions.extend(extract_questions(children, response_sets, cpid, cpl, csid, csl, template_id, template_name))

            return questions

        async def _export_questions():
            session, _ = create_async_session(token, concurrency=10)
            try:
                if mode == "Export all templates":
                    progress.progress(0.05, text="Fetching template list...")
                    templates = []
                    url = f"{BASE_URL}/feed/templates"
                    while url:
                        async with session.get(url) as resp:
                            resp.raise_for_status()
                            body = await resp.json()
                        templates.extend(body.get("data", []))
                        np = body.get("metadata", {}).get("next_page")
                        url = (np if np.startswith("http") else f"{BASE_URL}{np}") if np else None
                    templates = [t for t in templates if not t.get("archived", False)]
                else:
                    ids = [t.strip() for t in template_ids_input.replace(",", "\n").split("\n") if t.strip()]
                    templates = [{"id": tid, "name": f"Template {tid}"} for tid in ids]

                semaphore = asyncio.Semaphore(10)
                all_questions = []
                completed = 0
                total = len(templates)

                async def process_template(tmpl):
                    nonlocal completed
                    tid = tmpl.get("id", "")
                    tname = tmpl.get("name", "")
                    async with semaphore:
                        try:
                            async with session.get(f"{BASE_URL}/templates/v1/templates/{tid}") as resp:
                                completed += 1
                                progress.progress(0.1 + completed / total * 0.85, text=f"Processing {completed}/{total}...")
                                if resp.status != 200:
                                    return []
                                data = await resp.json()
                                template = data.get("template", {})
                                items = template.get("items", [])
                                rs_list = template.get("response_sets", [])
                                rs = {r.get("id"): r for r in rs_list if isinstance(r, dict)}
                                actual_name = template.get("name", tname)
                                return extract_questions(items, rs, template_id=tid, template_name=actual_name)
                        except Exception:
                            completed += 1
                            return []

                tasks = [process_template(t) for t in templates]
                results = await asyncio.gather(*tasks)
                for qs in results:
                    all_questions.extend(qs)

                return all_questions
            finally:
                await session.close()

        questions = run_async(_export_questions())
        progress.empty()

        if questions:
            for i, q in enumerate(questions):
                q["item_index"] = i
            df = pd.DataFrame(questions)
            display_dataframe_results(df, "template_questions.csv", f"Exported {len(questions):,} Questions")
        else:
            st.info("No questions found.")
