import streamlit as st
import pandas as pd
from io import BytesIO
import re

# ----------------------------------------------------------------------
# UI Configuration
# ----------------------------------------------------------------------
st.set_page_config(page_title="AutomationHub Data Processor", layout="wide")
st.title("AutomationHub Data Processor Grok - main4 + Stage1 Output")

# ----------------------------------------------------------------------
# Helper Constants & Functions
# ----------------------------------------------------------------------
NA_TOKENS = {"", "na", "n/a", "null", "nan", "<NA>", "none", "n.a."}

def norm_text(v):
    return "" if pd.isna(v) else str(v).strip()

def is_missing(v):
    return norm_text(v).lower() in NA_TOKENS

def fmt_date(d):
    if pd.isna(d): return ""
    if isinstance(d, str):
        d = pd.to_datetime(d, errors="coerce")
    return d.strftime("%m/%d/%Y") if pd.notna(d) else ""

def dedupe_preserve_order(tokens):
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
    pattern = re.compile(r'^solution deployed date(\.?\d*)?$', re.IGNORECASE)
    cols = [c for c in df.columns if pattern.match(c)]
    if not cols:
        df["Final Solution Deployed Date"] = ""
        return df, pd.Series([""] * len(df), dtype="string")

    df_dates = df[cols].apply(pd.to_datetime, errors="coerce")
    earliest = df_dates.min(axis=1, skipna=True)
    warns = ["Multiple Solution Deployed Dates in upstream data" 
             if len([v for v in row if pd.notna(v)]) > 1 and len(set(row.dropna())) > 1 else ""
             for _, row in df_dates.iterrows()]

    df["Final Solution Deployed Date"] = [fmt_date(d) for d in earliest]
    return df, pd.Series(warns, dtype="string")

# ----------------------------------------------------------------------
# 2) Final Process Execution Location
# ----------------------------------------------------------------------
def process_execution_location(df):
    location_patterns = [
        "in which location(s) is the process performed",
        "which location(s) is impacted by the automation solution",
        "which location is the process execution most closely associated with"
    ]
    cols = [c for c in df.columns if any(p in c.strip().lower() for p in location_patterns)]
    if not cols:
        df["Final Process Execution Location"] = ""
        return df, pd.Series([""] * len(df), dtype="string")

    finals, warns = [], []
    for _, row in df.iterrows():
        vals = [norm_text(row.get(c, "")) for c in cols if not is_missing(row.get(c, ""))]
        uniq = dedupe_preserve_order(vals)
        finals.append(uniq[0] if uniq else "")
        warns.append("Multiple Process Execution Locations in upstream data" if len(uniq) > 1 else "")
    df["Final Process Execution Location"] = finals
    return df, pd.Series(warns, dtype="string")

# ----------------------------------------------------------------------
# 3) Consolidated Tools + Tool for Reporting + Reason
# ----------------------------------------------------------------------
def process_tools(df):
    tool_cols = [c for c in df.columns if "what digital tools will be used" in c.strip().lower()]
    bu_col = next((c for c in df.columns if c.strip().lower() == "business unit"), None)
    div_col = next((c for c in df.columns if c.strip().lower() == "division"), None)
    idea_col = next((c for c in df.columns if c.strip().lower() == "idea type"), None)
    sol_cols = [c for c in df.columns if "solution type" in c.strip().lower()]
    date_col = next((c for c in df.columns if "date submitted" in c.strip().lower()), None)

    if not tool_cols:
        df["Consolidated Tools"] = ""
        df["Tool for Reporting"] = ""
        df["Reason"] = ""
        return df, pd.Series([""] * len(df), dtype="string")

    placeholders = {"other", "tbd", "other/tbd", "other - tbd", "tbd - other"}
    na_tokens = NA_TOKENS
    cons_list, tfr_list, reason_list = [], [], []

    for _, row in df.iterrows():
        # Build consolidated tools
        raw_tools = [norm_text(row.get(c, "")) for c in tool_cols if not is_missing(row.get(c, ""))]
        tokens = dedupe_preserve_order(raw_tools)
        consolidated = " - ".join(tokens) if tokens else ""

        # Special replacements
        consolidated = re.sub(r"\bOther\s*-\s*Process Reengineering\b", "Process Reengineering", consolidated, flags=re.IGNORECASE)
        consolidated = re.sub(r"\bProcess Reengineering\s*-\s*Other\b", "Process Reengineering", consolidated, flags=re.IGNORECASE)
        consolidated = re.sub(r"\bOther\s*-\s*Process Decommission\b", "Process Decommission", consolidated, flags=re.IGNORECASE)
        consolidated = re.sub(r"\bProcess Decommission\s*-\s*Other\b", "Process Decommission", consolidated, flags=re.IGNORECASE)

        # Context
        bu = norm_text(row.get(bu_col, "")).lower()
        div = norm_text(row.get(div_col, "")).lower()
        idea = norm_text(row.get(idea_col, "")).lower().replace(" ", "").replace("-", "")
        sol = ""
        for c in sol_cols:
            v = norm_text(row.get(c, ""))
            if v and v.lower() not in na_tokens:
                sol = v.lower().replace(" ", "").replace("-", "")
                break

        year_val = row.get(date_col)
        submitted_year = None
        if pd.notna(year_val):
            match = re.search(r'\b(19|20)\d{2}\b', str(year_val))
            if match:
                submitted_year = int(match.group(0))

        # Apply BU rules
        tfr = consolidated
        reason = "Default rule (no BU match)"
        if bu == "operations":
            if idea == "userled" and "processreengineering" in sol:
                tfr = "Process Reengineering"; reason = "Open PR Rule override"
            elif idea == "userled" and "systemicenhancements" in sol:
                tfr = "System Enhancements"; reason = "Ops System Enhancements rule"
            elif idea == "userled" and "tooling" in sol:
                tfr = consolidated; reason = "Ops Tooling rule"
            elif idea == "prodev":
                tfr = consolidated; reason = "Ops Pro-Dev rule"
            elif idea == "coreplatformtransformation":
                tfr = "Core Platform Transformation"; reason = "Ops CPT rule"
            else:
                tfr = consolidated; reason = "Ops default rule"
        elif bu == "company" and div == "finance":
            if idea == "newfinancetacticalautomation" and "systemicenhancements" in sol:
                tfr = consolidated; reason = "Finance Tactical rule"
            elif idea == "newfinancetechnologyledsolution":
                tfr = "Core Platform Transformation"; reason = "Finance Tech-Led override"
            else:
                tfr = consolidated; reason = "Finance default rule"

        # Consolidation logic
        if tfr == consolidated and consolidated:
            parts = dedupe_preserve_order([p.strip() for p in re.split(r"\s*-\s*", consolidated) if p.strip()])
            if len(parts) == 0:
                tfr = ""; reason = "No tools after consolidation"
            elif len(parts) == 1:
                tfr = parts[0]; reason = "Single tool"
            elif len(parts) == 2:
                a, b = parts
                al, bl = a.lower(), b.lower()
                if {al, bl} == {"process reengineering", "other"}:
                    tfr = "Process Reengineering"; reason = "Consolidation Case 2A"
                elif al == "process reengineering" and bl not in placeholders:
                    tfr = b; reason = "Consolidation Case 2B"
                elif bl == "process reengineering" and al not in placeholders:
                    tfr = a; reason = "Consolidation Case 2B"
                elif al in placeholders and bl not in placeholders:
                    tfr = b; reason = "Consolidation Case 2C"
                elif bl in placeholders and al not in placeholders:
                    tfr = a; reason = "Consolidation Case 2C"
                else:
                    tfr = " - ".join(sorted([a, b], key=str.lower))
                    reason = "Consolidation Case 2D"
            else:
                tfr = "Multiple"; reason = "More than 2 tools"

        # Fallback
        if not tfr.strip():
            is_ops_or_finance = (bu == "operations") or (bu == "company" and div == "finance")
            if submitted_year is not None and submitted_year <= 2023 and is_ops_or_finance:
                tfr = "UiPath"
                reason = "Fallback rule"
            elif submitted_year is not None and submitted_year <= 2023:
                tfr = "UiPath"
                reason = "Fallback rule"
            else:
                reason = "No date or invalid date" if submitted_year is None else "No fallback (not Ops or Finance)"

        tfr = tfr.replace(",", " - ").strip()

        cons_list.append(consolidated)
        tfr_list.append(tfr)
        reason_list.append(reason)

    df["Consolidated Tools"] = cons_list
    df["Tool for Reporting"] = tfr_list
    df["Reason"] = reason_list
    return df, pd.Series([""] * len(df), dtype="string")

# ----------------------------------------------------------------------
# Pipeline
# ----------------------------------------------------------------------
def merge_all(df):
    df1, w1 = process_solution_deployed_date(df.copy())
    df2, w2 = process_execution_location(df1)
    df3, w3 = process_tools(df2)
    df3["Processing Warnings"] = [", ".join(filter(None, [a.strip(), b.strip(), c.strip()])) 
                                  for a, b, c in zip(w1, w2, w3)]
    return df3

# ----------------------------------------------------------------------
# Stage 1 Required Columns (Exact Order & Names)
# ----------------------------------------------------------------------
STAGE1_COLUMNS = [
    "Automation Hub ID", "Created On", "Annual Capacity Created (Hrs)_Previous Month", "Annual Capacity Group",
    "Annual Hours based on Volume", "Annual Hours Number", "Automation Hub Link", "Automation Hub Phase",
    "Automation Hub Status", "Automation Name", "Automation Potential", "AutomatioHub Phase_Previous Month",
    "AutomatioHub Status_Previous Month", "AutomatioHubData_Stage1", "Benefiting Division", "Business Unit",
    "Calculated Capacity Created Number", "Capacity created_Range", "Consolidated Actual Capacity",
    "Consolidated Tools", "Created By", "Created By (Delegate)", "Date Submitted", "Decommissioned date",
    "Department", "Derived Process Location", "Derived Solution Deployed Date", "Division",
    "Estimated Delivery Date", "Expected Capacity Saves Annual Hrs Number", "Final Tools Classification",
    "Idea Submitter BU", "Idea Submitter Department", "Idea Submitter Division", "Idea Submitter E mail",
    "Idea Submitter Location", "Idea Submitter Login Id", "Idea Submitter Name", "Idea Submitter Super Department",
    "Idea Type", "Import Sequence Number", "is considered for YTD calculation", "is SDLC followed",
    "Last Modified Date", "Modified By", "Modified By (Delegate)", "Modified On", "New Short Phase",
    "Owner", "Owning Business Unit", "Owning Team", "Owning User", "Process Execution Location",
    "Process Outcome", "Process Owner", "Process Warnings", "Record Created On", "Short Phase",
    "Short Phase Number", "Solution Depoyed Date", "Solution Type", "Status", "Status Reason",
    "Sub Department", "Submitter's Business Unit", "Submitter's Department", "Super Department",
    "Time Zone Rule Version Number", "Tool for Reporting", "Tool_Used_Combined", "tools_multiple",
    "Type of Automation", "UTC Conversion Time Zone Code", "Version Number"
]

# ----------------------------------------------------------------------
# Streamlit App
# ----------------------------------------------------------------------
uploaded_file = st.file_uploader("Upload your Excel/CSV file", type=["xlsx", "csv"])

if uploaded_file:
    try:
        df_in = pd.read_excel(uploaded_file) if not uploaded_file.name.lower().endswith(".csv") else pd.read_csv(uploaded_file)
    except Exception as e:
        st.error(f"Error reading file: {e}")
        st.stop()

    if df_in.empty:
        st.error("Uploaded file is empty.")
        st.stop()

    with st.spinner("Processing data..."):
        df_out = merge_all(df_in.copy())

    st.success("Processed successfully!")

    # === Output 1: Main Processed File ===
    with st.expander("Preview (first 25 rows)", expanded=True):
        st.dataframe(df_out.head(25), use_container_width=True)

    # === Output 2: Stage1 Data (67 columns in exact order) ===
    stage1_df = pd.DataFrame(columns=STAGE1_COLUMNS)
    for col in STAGE1_COLUMNS:
        if col in df_out.columns:
            stage1_df[col] = df_out[col]
        elif col == "Derived Solution Deployed Date":
            stage1_df[col] = df_out.get("Final Solution Deployed Date", "")
        elif col == "Process Execution Location":
            stage1_df[col] = df_out.get("Final Process Execution Location", "")
        else:
            stage1_df[col] = ""

    # Fill Tool for Reporting (already exists)
    stage1_df["Tool for Reporting"] = df_out["Tool for Reporting"]

    # === Export Both Files ===
    buf1 = BytesIO()
    buf2 = BytesIO()

    with pd.ExcelWriter(buf1, engine="openpyxl") as writer:
        df_out.to_excel(writer, index=False, sheet_name="Processed")
    buf1.seek(0)

    with pd.ExcelWriter(buf2, engine="openpyxl") as writer:
        stage1_df.to_excel(writer, index=False, sheet_name="Stage1_Data")
    buf2.seek(0)

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            label="Download Main Processed File",
            data=buf1,
            file_name="processed_automationhub.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    with col2:
        st.download_button(
            label="Download automation_stage1_data.xlsx",
            data=buf2,
            file_name="automation_stage1_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    if df_out["Processing Warnings"].str.strip().any():
        st.warning("Some rows have processing warnings:")
        st.dataframe(df_out[df_out["Processing Warnings"].str.strip() != ""][["Processing Warnings"]])
