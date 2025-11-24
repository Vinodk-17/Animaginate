import streamlit as st
import pandas as pd
from io import BytesIO
import re

# ----------------------------------------------------------------------
# UI Configuration
# ----------------------------------------------------------------------
st.set_page_config(page_title="AutomationHub Data Processor", layout="wide")
st.title("AutomationHub Data Processor Grok - Final v5")

# ----------------------------------------------------------------------
# 1. TEST / EXCLUDED AUTOMATION NAMES (Hard Remove)
# ----------------------------------------------------------------------
EXCLUDED_AUTOMATION_NAMES = {
    "Squad", "test", "6587", "6508", "LCD_INV_TEST_MUM 1", "6468", "Test LCDI", "6460",
    "TEST-LCD", "5975", "Testing Workflow", "5972", "test tech", "4636", "test WM", "4609",
    "Test Roundoff", "4467", "Ops Test", "2161", "Test Trade Options Only for testing 1504",
    "Test Tuesday", "1503", "Only for Test", "1502", "Test Automation for GRC", "1342",
    "test2", "993", "992", "Test AH", "654"
}

# ----------------------------------------------------------------------
# 2. Special Automation Names → Force "Other" in Tool for Reporting
# ----------------------------------------------------------------------
FORCE_OTHER_AUTOMATION_NAMES = {
    "EPR Automation - E*TRADE Integration",
    "Elimination of Cyber Ops L1 Support",
    "EPR Robotics Process Automation",
    "Self Serve Bulk Access Request.",
    "Modern Authentication SAML Cert Renewal Self-Service",
    "WSA Migration to GetAccess for Automated Provisioning",
    "Salesforce Integration",
    "EBOSS Integration",
    "External Site Migration to eNav"
}

# ----------------------------------------------------------------------
# Helper Functions
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
        return df, pd.Series([""] * len(df), dtype="string")

    df_dates = df[cols].apply(pd.to_datetime, errors="coerce")
    earliest = df_dates.min(axis=1, skipna=True)
    warns = ["Multiple Solution Deployed Dates in upstream data" 
             if len(vals) > 1 and len(set(vals)) > 1 else "" 
             for vals in (df_dates.iloc[i].dropna().tolist() for i in range(len(df)))]
    
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
        return df, pd.Series([""] * len(df), dtype="string")

    finals, warns = [], []
    for _, row in df.iterrows():
        vals = [norm_text(row.get(c, "")) for c in cols if not is_missing(row.get(c, ""))]
        uniq = []
        seen = set()
        for v in vals:
            vn = v.strip().lower()
            if vn not in seen:
                seen.add(vn)
                uniq.append(v)
        finals.append(uniq[0] if len(uniq) == 1 else (uniq[0] if uniq else ""))
        warns.append("Multiple Process Execution Locations in upstream data" if len(uniq) > 1 else "")
    df["Final Process Execution Location"] = finals
    return df, pd.Series(warns, dtype="string")

# ----------------------------------------------------------------------
# 3) Consolidated Tools + Tool for Reporting + Reason (MAIN LOGIC)
# ----------------------------------------------------------------------
def process_tools(df):
    tool_cols = [c for c in df.columns if "what digital tools will be used" in c.strip().lower()]
    bu_col = next((c for c in df.columns if c.strip().lower() == "business unit"), None)
    div_col = next((c for c in df.columns if c.strip().lower() == "division"), None)
    idea_col = next((c for c in df.columns if c.strip().lower() == "idea type"), None)
    sol_cols = [c for c in df.columns if "solution type" in c.strip().lower()]
    date_col = next((c for c in df.columns if "date submitted" in c.strip().lower()), None)
    auto_name_col = next((c for c in df.columns if "automation name" in c.strip().lower()), None)

    if not tool_cols:
        df["Consolidated Tools"] = ""
        df["Tool for Reporting"] = ""
        df["Reason"] = ""
        return df, pd.Series([""] * len(df), dtype="string")

    placeholders = {"other", "tbd", "other/tbd", "other - tbd", "tbd - other", "other/tdb"}
    cons_list, tfr_list, reason_list, warns = [], [], [], []

    for _, row in df.iterrows():
        auto_name = norm_text(row.get(auto_name_col, ""))

        # === FORCE "Other" for specific automation names ===
        if auto_name in FORCE_OTHER_AUTOMATION_NAMES:
            cons_list.append("")
            tfr_list.append("Other")
            reason_list.append("Forced Other (Special Automation Name)")
            warns.append("")
            continue

        # === Build raw tools ===
        raw_tools = []
        for c in tool_cols:
            v = norm_text(row.get(c, ""))
            if v and v.lower() not in NA_TOKENS:
                raw_tools.append(v.strip())

        seen = set()
        tokens = []
        for t in raw_tools:
            tl = t.lower()
            if tl not in seen:
                seen.add(tl)
                tokens.append(t)

        # === Standardization ===
        standardized = []
        for t in tokens:
            t = t.replace("powerbi", "Power BI", 1) if "powerbi" in t.lower() else t
            t = t.replace("Intelligent Document Processing", "Intelligent Document Processing (IDP)")
            standardized.append(t)
        tokens = standardized

        consolidated = " - ".join(tokens) if tokens else ""

        # Special replacements
        consolidated = re.sub(r"\bOther\s*-\s*Process Reengineering\b", "Process Reengineering", consolidated, flags=re.IGNORECASE)
        consolidated = re.sub(r"\bProcess Reengineering\s*-\s*Other\b", "Process Reengineering", consolidated, flags=re.IGNORECASE)

        # === NEW: Process Reengineering + Other Logic ===
        parts = [p.strip() for p in re.split(r"\s*-\s*", consolidated) if p.strip()]
        parts_lower = [p.lower() for p in parts]

        has_pr = any("process reengineering" in p.lower() for p in parts)
        has_other = any(p.lower() in placeholders for p in parts)
        non_other_tools = [p for p in parts if p.lower() not in placeholders and "process reengineering" not in p.lower()]

        if has_pr:
            if has_other and not non_other_tools:
                # Only PR + Other/TBD → "Other"
                tfr = "Other"
                reason = "PR + Other/TBD only → Other"
            elif has_other and non_other_tools:
                # PR + Other + real tools → "Other Tool (X, Y)"
                tool_str = " - ".join(sorted(non_other_tools, key=str.lower))
                tfr = f"Other Tool ({tool_str})"
                reason = "PR + Other + real tools → Other Tool"
            else:
                # Only PR → keep as is
                tfr = consolidated
                reason = "Process Reengineering only"
        else:
            tfr = consolidated
            reason = "Standard consolidation"

        # Alphabetical sort for exactly 2 non-special tools
        if not has_pr and len(parts) == 2 and all(p.lower() not in placeholders for p in parts):
            tfr = " - ".join(sorted(parts, key=str.lower))
            reason = "Two tools → sorted alphabetically"

        # Fallback UiPath
        if not tfr.strip():
            bu = norm_text(row.get(bu_col, "")).lower()
            div = norm_text(row.get(div_col, "")).lower()
            year_val = row.get(date_col)
            submitted_year = None
            if pd.notna(year_val):
                match = re.search(r'\b(19|20)\d{2}\b', str(year_val))
                if match:
                    submitted_year = int(match.group(0))

            is_ops_or_finance = (bu == "operations") or (bu == "company" and div == "finance")
            if submitted_year is not None and submitted_year <= 2023 and is_ops_or_finance:
                tfr = "UiPath"
                reason = "Fallback rule"

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
# Pipeline
# ----------------------------------------------------------------------
def merge_all(df):
    # Remove test/excluded automation names FIRST
    auto_name_col = next((c for c in df.columns if "automation name" in c.strip().lower()), None)
    if auto_name_col:
        df = df[~df[auto_name_col].astype(str).isin(EXCLUDED_AUTOMATION_NAMES)].reset_index(drop=True)

    df1, w1 = process_solution_deployed_date(df.copy())
    df2, w2 = process_execution_location(df1)
    df3, w3 = process_tools(df2)

    df3["Processing Warnings"] = [
        ", ".join(filter(None, [a.strip(), b.strip(), c.strip()]))
        for a, b, c in zip(w1, w2, w3)
    ]
    return df3

# ----------------------------------------------------------------------
# Streamlit App
# ----------------------------------------------------------------------
uploaded_file = st.file_uploader("Upload your Excel/CSV file", type=["xlsx", "csv"])

if uploaded_file:
    try:
        df_in = pd.read_excel(uploaded_file) if not uploaded_file.name.lower().endswith(".csv") else pd.read_csv(uploaded_file)
    except Exception as e:
        st.error(f"Error: {e}")
        st.stop()

    if df_in.empty:
        st.error("File is empty.")
        st.stop()

    with st.spinner("Processing..."):
        df_out = merge_all(df_in)

    st.success("Processed Successfully!")

    with st.expander("Preview (25 rows)", expanded=True):
        st.dataframe(df_out.head(25), use_container_width=True)

    with st.expander("Full Data", expanded=False):
        st.dataframe(df_out, use_container_width=True)

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_out.to_excel(writer, index=False, sheet_name="Processed")
    buf.seek(0)

    st.download_button(
        label="Download Processed File",
        data=buf,
        file_name="AutomationHub_Processed_Final.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    if df_out["Processing Warnings"].str.strip().any():
        st.warning("Warnings found:")
        st.dataframe(df_out[df_out["Processing Warnings"].str.strip() != ""][["Processing Warnings"]])
