# new more update 

import streamlit as st
import pandas as pd
from io import BytesIO
import re

# ----------------------------------------------------------------------
# UI Configuration
# ----------------------------------------------------------------------
st.set_page_config(page_title="AutomationHub Data Processor", layout="wide")
st.title("AutomationHub Data Processor Grok - main4")

# ----------------------------------------------------------------------
# Helper Constants & Functions
# ----------------------------------------------------------------------
NA_TOKENS = {"", "na", "n/a", "null", "nan", "<NA>", "none", "n.a."}

def norm_text(v):
    """Normalize any value to a clean string; treat missing/NA as empty."""
    return "" if pd.isna(v) else str(v).strip()

def is_missing(v):
    """Check if a value is considered missing or placeholder."""
    return norm_text(v).lower() in NA_TOKENS

def fmt_date(d):
    """Format a date to MM/DD/YYYY; gracefully handle invalid inputs."""
    if pd.isna(d):
        return ""
    if isinstance(d, str):
        d = pd.to_datetime(d, errors="coerce")
    return d.strftime("%m/%d/%Y") if pd.notna(d) else ""

def dedupe_preserve_order(tokens):
    """Remove duplicates while preserving original order (case-insensitive)."""
    seen = set()
    out = []
    for t in tokens:
        tl = t.lower()
        if tl not in seen:
            seen.add(tl)
            out.append(t)
    return out

# ----------------------------------------------------------------------
# 1) Final Solution Deployed Date
# ----------------------------------------------------------------------
def process_solution_deployed_date(df):
    """
    Identify all columns matching 'Solution Deployed Date[.n]' pattern,
    take the earliest valid date per row, and format it.
    Warn if multiple distinct dates exist in the same row.
    """
    pattern = re.compile(r'^solution deployed date(\.?\d*)?$', re.IGNORECASE)
    cols = [c for c in df.columns if pattern.match(c)]
    if not cols:
        return df, pd.Series([""] * len(df), dtype="string")

    df_dates = df[cols].apply(pd.to_datetime, errors="coerce")
    earliest = df_dates.min(axis=1, skipna=True)

    warns = []
    for i in range(len(df)):
        vals = [v for v in df_dates.iloc[i].tolist() if pd.notna(v)]
        if len(vals) > 1 and len(set(vals)) > 1:
            warns.append("Multiple Solution Deployed Dates in upstream data")
        else:
            warns.append("")

    df["Final Solution Deployed Date"] = [fmt_date(d) for d in earliest]
    return df, pd.Series(warns, dtype="string")

# ----------------------------------------------------------------------
# 2) Final Process Execution Location
# ----------------------------------------------------------------------
def process_execution_location(df):
    """
    Consolidate location columns from multiple possible names:
    - In which location(s) is the process performed?
    - Which location(s) is impacted by the automation solution?
    - Which location is the process execution most closely associated with?
    Dedupe values (case-insensitive), keep first occurrence if multiple.
    """
    # Flexible column matching
    location_patterns = [
        "in which location(s) is the process performed",
        "which location(s) is impacted by the automation solution",
        "which location is the process execution most closely associated with"
    ]
    cols = [
        c for c in df.columns
        if any(p in c.strip().lower() for p in location_patterns)
    ]

    if not cols:
        return df, pd.Series([""] * len(df), dtype="string")

    finals, warns = [], []
    for _, row in df.iterrows():
        vals = []
        for c in cols:
            v = norm_text(row.get(c, ""))
            if not is_missing(v):
                vals.append(v)

        # Dedupe while preserving order
        uniq_norm = []
        seen = set()
        for v in vals:
            vn = v.strip().lower()
            if vn not in seen:
                seen.add(vn)
                uniq_norm.append(v)

        if len(vals) == 0:
            finals.append("")
            warns.append("")
        elif len(uniq_norm) == 1:
            finals.append(vals[0].strip())
            warns.append("")
        else:
            finals.append(vals[0].strip())
            warns.append("Multiple Process Execution Locations in upstream data")

    df["Final Process Execution Location"] = finals
    return df, pd.Series(warns, dtype="string")

# ----------------------------------------------------------------------
# 3) Consolidated Tools + Tool for Reporting + Reason
# ----------------------------------------------------------------------
def process_tools(df):
    """
    Core logic with updated column mapping:
    - Tool columns: All named 'What digital tools will be used?'
    - Solution Type: Use non-N/A from 'Solution Type' or 'Solution Type New'
    - Final Tool for Reporting: Alphabetically sorted when multiple
    """
    # --- Flexible Tool Column Detection ---
    tool_cols = [c for c in df.columns if "what digital tools will be used" in c.strip().lower()]

    # --- Contextual Columns ---
    bu_col    = next((c for c in df.columns if c.strip().lower() == "business unit"), None)
    div_col   = next((c for c in df.columns if c.strip().lower() == "division"), None)
    idea_col  = next((c for c in df.columns if c.strip().lower() == "idea type"), None)

    # Solution Type: Prefer non-N/A from either column
    sol_cols = [c for c in df.columns if "solution type" in c.strip().lower()]
    date_col  = next((c for c in df.columns if "date submitted" in c.strip().lower()), None)

    if not tool_cols:
        df["Consolidated Tools"] = ""
        df["Tool for Reporting"] = ""
        df["Reason"] = ""
        return df, pd.Series([""] * len(df), dtype="string")

    placeholders = {"other", "tbd", "other/tbd", "other - tbd", "tbd - other"}
    na_tokens = NA_TOKENS

    cons_list, tfr_list, reason_list, warns = [], [], [], []

    for _, row in df.iterrows():
        # === Step 1: Build Consolidated Tools ===
        raw_tools = []
        for c in tool_cols:
            v = norm_text(row.get(c, ""))
            if v.lower() not in na_tokens and v.strip():
                raw_tools.append(v.strip())

        seen = set()
        tokens = []
        for t in raw_tools:
            tl = t.lower()
            if tl not in seen:
                seen.add(tl)
                tokens.append(t)

        consolidated = " - ".join(tokens) if tokens else ""

        # Special replacements
        consolidated = re.sub(r"\bOther\s*-\s*Process Reengineering\b", "Process Reengineering", consolidated, flags=re.IGNORECASE)
        consolidated = re.sub(r"\bProcess Reengineering\s*-\s*Other\b", "Process Reengineering", consolidated, flags=re.IGNORECASE)
        consolidated = re.sub(r"\bOther\s*-\s*Process Decommission\b", "Process Decommission", consolidated, flags=re.IGNORECASE)
        consolidated = re.sub(r"\bProcess Decommission\s*-\s*Other\b", "Process Decommission", consolidated, flags=re.IGNORECASE)

        # === Normalize Context ===
        bu   = norm_text(row.get(bu_col, "")).strip().lower()
        div  = norm_text(row.get(div_col, "")).strip().lower()
        idea = norm_text(row.get(idea_col, "")).strip().lower().replace(" ", "").replace("-", "")

        # Solution Type: First non-N/A from any solution column
        sol = ""
        for c in sol_cols:
            v = norm_text(row.get(c, ""))
            if v and v.lower() not in na_tokens:
                sol = v.lower().replace(" ", "").replace("-", "")
                break

        # === Extract Year (year-only input) ===
        year_val = row.get(date_col)
        submitted_year = None
        if pd.notna(year_val):
            match = re.search(r'\b(19|20)\d{2}\b', str(year_val))
            if match:
                submitted_year = int(match.group(0))

        # === Step 2: Apply BU/Division Rules ===
        tfr = consolidated
        reason = "Default rule (no BU match)"

        if bu == "operations":
            if idea == "userled" and "processreengineering" in sol:
                tfr = "Process Reengineering"
                reason = "Open PR Rule override"
            elif idea == "userled" and "systemicenhancements" in sol:
                tfr = "System Enhancements"
                reason = "Ops System Enhancements rule"
            elif idea == "userled" and "tooling" in sol:
                tfr = consolidated
                reason = "Ops Tooling rule"
            elif idea == "prodev":
                tfr = consolidated
                reason = "Ops Pro-Dev rule"
            elif idea == "coreplatformtransformation":
                tfr = "Core Platform Transformation"
                reason = "Ops CPT rule"
            else:
                tfr = consolidated
                reason = "Ops default rule"

        elif bu == "company" and div == "finance":
            if idea == "newfinancetacticalautomation" and "systemicenhancements" in sol:
                tfr = consolidated
                reason = "Finance Tactical rule"
            elif idea == "newfinancetechnologyledsolution":
                tfr = "Core Platform Transformation"
                reason = "Finance Tech-Led override"
            else:
                tfr = consolidated
                reason = "Finance default rule"
        else:
            tfr = consolidated
            reason = "Default rule (no BU match)"

        # === Step 3: Consolidation Logic ===
        if tfr == consolidated and consolidated:
            parts = [p.strip() for p in re.split(r"\s*-\s*", consolidated) if p.strip()]
            parts = dedupe_preserve_order(parts)

            if len(parts) == 0:
                tfr = ""
                reason = "No tools after consolidation"
            elif len(parts) == 1:
                tfr = parts[0]
                reason = "Single tool"
            elif len(parts) == 2:
                a, b = parts
                al, bl = a.lower(), b.lower()
                if {al, bl} == {"process reengineering", "other"}:
                    tfr = "Process Reengineering"
                    reason = "Consolidation Case 2A"
                elif al == "process reengineering" and bl not in placeholders:
                    tfr = b
                    reason = "Consolidation Case 2B"
                elif bl == "process reengineering" and al not in placeholders:
                    tfr = a
                    reason = "Consolidation Case 2B"
                elif al in placeholders and bl not in placeholders:
                    tfr = b
                    reason = "Consolidation Case 2C"
                elif bl in placeholders and al not in placeholders:
                    tfr = a
                    reason = "Consolidation Case 2C"
                else:
                    # Alphabetical sort for 2 tools
                    sorted_pair = " - ".join(sorted([a, b], key=str.lower))
                    tfr = sorted_pair
                    reason = "Consolidation Case 2D"
            else:
                tfr = "Multiple"
                reason = "More than 2 tools"

        # === Step 4: Fallback Logic ===
        if not tfr.strip():
            is_ops_or_finance = (bu == "operations") or (bu == "company" and div == "finance")
            if submitted_year is not None and submitted_year <= 2023 and is_ops_or_finance:
                tfr = "UiPath"
                reason = "Fallback rule"
            elif submitted_year is not None and submitted_year <= 2023:
                tfr = "UiPath"
                reason = "Fallback rule"
            else:
                if submitted_year is None:
                    reason = "No date or invalid date"
                else:
                    reason = "No fallback (not Ops or Finance)"

        # Final cleanup
        tfr = tfr.replace(",", " - ").strip()

        cons_list.append(consolidated)
        tfr_list.append(tfr)
        reason_list.append(reason)
        warns.append("")

    df["Consolidated Tools"] = cons_list
    df["Tool for Reporting"] = tfr_list
    df["Reason"] = reason_list
    return df, pd.Series(warns, dtype="string")

# ----------------------------------------------------------------------
# Pipeline Orchestration
# ----------------------------------------------------------------------
def merge_all(df):
    df1, w1 = process_solution_deployed_date(df.copy())
    df2, w2 = process_execution_location(df1)
    df3, w3 = process_tools(df2)

    df3["Processing Warnings"] = [
        ", ".join(filter(None, [a.strip(), b.strip(), c.strip()]))
        for a, b, c in zip(w1, w2, w3)
    ]
    return df3

# ----------------------------------------------------------------------
# Streamlit App Runtime
# ----------------------------------------------------------------------
uploaded_file = st.file_uploader("Upload your Excel/CSV file", type=["xlsx", "csv"])

if uploaded_file:
    try:
        if uploaded_file.name.lower().endswith(".csv"):
            df_in = pd.read_csv(uploaded_file)
        else:
            df_in = pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"Error reading file: {e}")
        st.stop()

    if df_in.empty:
        st.error("Uploaded file is empty.")
        st.stop()

    with st.spinner("Processing data..."):
        df_out = merge_all(df_in)

    st.success("Processed successfully!")

    with st.expander("Preview (first 25 rows)", expanded=True):
        st.dataframe(df_out.head(25), use_container_width=True)

    with st.expander("Full Processed Data", expanded=False):
        st.dataframe(df_out, use_container_width=True)

    df_export = df_out.copy().fillna("").astype(str)
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_export.to_excel(writer, index=False, sheet_name="Processed")
    buf.seek(0)

    st.download_button(
        label="Download Processed Excel",
        data=buf,
        file_name="processed_automationhub.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    if df_out["Processing Warnings"].str.strip().any():
        st.warning("Some rows have processing warnings:")
        warning_df = df_out[df_out["Processing Warnings"].str.strip() != ""][["Processing Warnings"]]
        st.dataframe(warning_df)
