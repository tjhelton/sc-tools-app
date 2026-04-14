"""Courses tools - assign courses to sites."""

import pandas as pd
import requests
import streamlit as st

from core.api import BASE_URL, get_headers, get_token
from core.ui import check_token, display_results, file_uploader, tool_header

st.header("Courses")
if not check_token():
    st.stop()

tool_header(
    "Assign Courses to Sites",
    "Assign training courses to sites in bulk. The tool automatically groups "
    "assignments by course and sends them as batches.",
    requires_csv=True,
    csv_columns=["course_id", "site_id"],
)

df = file_uploader(
    "Upload CSV with course_id and site_id",
    required_columns=["course_id", "site_id"],
    key="assign_courses_csv",
)

if df is not None and st.button("Assign Courses", key="run_assign_courses"):
    token = get_token()
    records = df.fillna("").to_dict("records")

    # Group by course
    course_sites = {}
    for row in records:
        cid = str(row["course_id"]).strip()
        sid = str(row["site_id"]).strip()
        if cid and sid:
            course_sites.setdefault(cid, []).append(sid)

    progress = st.progress(0, text="Assigning courses...")
    results = []
    total = len(course_sites)

    for i, (course_id, site_ids) in enumerate(course_sites.items()):
        assignments = [
            {"type": "ASSIGNMENT_TYPE_SITE", "id": sid, "is_assigned": True}
            for sid in site_ids
        ]
        try:
            resp = requests.put(
                f"{BASE_URL}/training/courses/v1/{course_id}/assignments",
                json={"assignments": assignments},
                headers=get_headers(token),
                timeout=30,
            )
            resp.raise_for_status()
            results.append({
                "course_id": course_id,
                "sites_assigned": len(site_ids),
                "status": "SUCCESS",
                "error": "",
            })
        except Exception as e:
            results.append({
                "course_id": course_id,
                "sites_assigned": 0,
                "status": "ERROR",
                "error": str(e),
            })
        progress.progress((i + 1) / total)

    progress.empty()
    display_results(results, "assign_courses_results.csv")
