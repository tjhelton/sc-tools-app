"""SafetyCulture Tools - Home Page."""

import streamlit as st

st.set_page_config(
    page_title="SafetyCulture Tools",
    page_icon="SC",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize session state
if "api_token" not in st.session_state:
    st.session_state.api_token = ""


def main():
    st.title("SafetyCulture Tools")
    st.markdown(
        "A collection of bulk operations tools for the SafetyCulture platform. "
        "Select a category from the sidebar to get started."
    )

    st.divider()

    # --- API Token Setup ---
    st.subheader("API Token")
    st.markdown(
        "Enter your SafetyCulture API token below. "
        "Your token is stored only for this session and never saved to disk."
    )

    token_input = st.text_input(
        "API Token",
        value=st.session_state.api_token,
        type="password",
        placeholder="Paste your SafetyCulture API token here...",
    )

    col1, col2 = st.columns([1, 4])

    with col1:
        if st.button("Save & Validate", type="primary"):
            if not token_input.strip():
                st.error("Please enter a token.")
            else:
                with st.spinner("Validating token..."):
                    from core.api import validate_token

                    valid, message = validate_token(token_input.strip())
                if valid:
                    st.session_state.api_token = token_input.strip()
                    st.success(message)
                else:
                    st.error(message)

    with col2:
        if st.session_state.api_token:
            st.success("Token is set. You're ready to use the tools.")
        else:
            st.info("No token set yet.")

    st.divider()

    # --- Tool Overview ---
    st.subheader("Available Tools")

    tools = [
        {
            "icon": "clipboard-check",
            "name": "Actions",
            "description": "Export, update status, delete actions, and manage action schedules.",
            "count": 5,
        },
        {
            "icon": "box-seam",
            "name": "Assets",
            "description": "Export assets and asset types, bulk update fields, and delete assets.",
            "count": 4,
        },
        {
            "icon": "search",
            "name": "Inspections",
            "description": "Archive, unarchive, delete inspections. Export PDFs and location changes.",
            "count": 7,
        },
        {
            "icon": "geo-alt",
            "name": "Sites",
            "description": "Create, delete sites. Find inactive sites. Manage site user access.",
            "count": 4,
        },
        {
            "icon": "file-earmark-text",
            "name": "Templates",
            "description": "Archive templates. Export access rules and template questions.",
            "count": 3,
        },
        {
            "icon": "people",
            "name": "Users",
            "description": "Bulk deactivate users. Export users with custom field values.",
            "count": 2,
        },
        {
            "icon": "mortarboard",
            "name": "Courses",
            "description": "Assign training courses to sites in bulk.",
            "count": 1,
        },
        {
            "icon": "person-lines-fill",
            "name": "Groups",
            "description": "Create groups in bulk. Export group member details.",
            "count": 2,
        },
        {
            "icon": "exclamation-triangle",
            "name": "Issues",
            "description": "Export issue public links and issue relationships.",
            "count": 2,
        },
        {
            "icon": "building",
            "name": "Organizations",
            "description": "Export contractor company details.",
            "count": 1,
        },
        {
            "icon": "calendar-event",
            "name": "Schedules",
            "description": "Export and update legacy schedule items.",
            "count": 2,
        },
    ]

    cols = st.columns(3)
    for i, tool in enumerate(tools):
        with cols[i % 3]:
            st.markdown(
                f"**{tool['name']}** ({tool['count']} tools)  \n"
                f"{tool['description']}"
            )

    st.divider()

    # --- Quick start guide ---
    st.subheader("Quick Start")
    st.markdown(
        """
1. **Paste your API token** above and click "Save & Validate"
2. **Pick a category** from the sidebar (e.g., Inspections)
3. **Choose a tool** from the tabs within the category
4. **Upload your CSV** if the tool requires one (each tool shows required columns)
5. **Click Run** and watch the progress
6. **Download the results** when complete
"""
    )

    st.markdown(
        """
---
*Built on the [SafetyCulture API](https://developer.safetyculture.com/).
See the original scripts in the `scripts/` directory for advanced usage.*
"""
    )


if __name__ == "__main__":
    main()
