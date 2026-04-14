"""Shared UI components for the SafetyCulture Tools app."""

import io
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st


def check_token() -> bool:
    """Check if API token is set. Show warning and return False if not."""
    if not st.session_state.get("api_token"):
        st.warning("Please enter your API token on the **Home** page first.")
        return False
    return True


def page_setup(title: str, icon: str = ""):
    """Standard page setup with token check."""
    display = f"{icon} {title}" if icon else title
    st.header(display)
    return check_token()


def file_uploader(
    label: str = "Upload input CSV",
    required_columns: Optional[List[str]] = None,
    key: Optional[str] = None,
    help_text: Optional[str] = None,
) -> Optional[pd.DataFrame]:
    """Upload and validate a CSV file. Returns DataFrame or None."""
    help_msg = help_text or ""
    if required_columns:
        help_msg += f"\n\nRequired columns: `{', '.join(required_columns)}`"

    uploaded = st.file_uploader(label, type=["csv"], key=key, help=help_msg.strip())
    if uploaded is None:
        return None

    try:
        df = pd.read_csv(uploaded).fillna("")
    except Exception as e:
        st.error(f"Error reading CSV: {e}")
        return None

    if required_columns:
        missing = [c for c in required_columns if c not in df.columns]
        if missing:
            st.error(f"Missing required columns: {', '.join(missing)}")
            st.info(f"Found columns: {', '.join(df.columns.tolist())}")
            return None

    st.success(f"Loaded {len(df):,} rows with columns: {', '.join(df.columns.tolist())}")
    with st.expander("Preview data", expanded=False):
        st.dataframe(df.head(20), use_container_width=True)

    return df


def display_results(
    results: List[Dict],
    filename: str = "results.csv",
    title: str = "Results",
):
    """Display results table with download button."""
    if not results:
        st.info("No results to display.")
        return

    df = pd.DataFrame(results)
    st.subheader(title)

    # Summary stats
    if "status" in df.columns:
        col1, col2, col3 = st.columns(3)
        total = len(df)
        success = len(df[df["status"].str.upper().isin(["SUCCESS", "OK"])])
        errors = total - success
        col1.metric("Total", f"{total:,}")
        col2.metric("Success", f"{success:,}")
        col3.metric("Errors", f"{errors:,}")
    elif "result" in df.columns:
        col1, col2, col3 = st.columns(3)
        total = len(df)
        success = len(df[df["result"].str.upper().isin(["SUCCESS", "OK"])])
        errors = total - success
        col1.metric("Total", f"{total:,}")
        col2.metric("Success", f"{success:,}")
        col3.metric("Errors", f"{errors:,}")

    st.dataframe(df, use_container_width=True)

    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        f"Download {filename}",
        csv_bytes,
        file_name=filename,
        mime="text/csv",
    )


def display_dataframe_results(
    df: pd.DataFrame,
    filename: str = "results.csv",
    title: str = "Results",
):
    """Display a DataFrame with download button."""
    if df is None or df.empty:
        st.info("No results to display.")
        return

    st.subheader(title)
    col1, _ = st.columns([1, 3])
    col1.metric("Total Records", f"{len(df):,}")

    st.dataframe(df, use_container_width=True)

    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        f"Download {filename}",
        csv_bytes,
        file_name=filename,
        mime="text/csv",
    )


def confirm_destructive(message: str, key: str) -> bool:
    """Confirmation for destructive operations. Returns True if confirmed."""
    st.warning(message)
    confirmation = st.text_input(
        'Type "CONFIRM" to proceed:',
        key=f"confirm_{key}",
    )
    return confirmation == "CONFIRM"


def timestamped_filename(prefix: str, extension: str = "csv") -> str:
    """Generate a timestamped filename."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{ts}.{extension}"


def tool_header(name: str, description: str, requires_csv: bool = False, csv_columns: Optional[List[str]] = None):
    """Display a consistent tool header with documentation."""
    st.markdown(f"**{name}**")
    st.markdown(description)
    if requires_csv and csv_columns:
        st.info(f"**Required CSV columns:** `{', '.join(csv_columns)}`")
    elif requires_csv:
        st.info("This tool requires a CSV file upload.")
