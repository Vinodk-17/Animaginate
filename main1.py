import streamlit as st
import pandas as pd
from io import BytesIO

# ---------- Helpers ----------
NA_TOKENS = {"", "na", "n/a", "null", "nan"}

def is_missing(val):
    if pd.isna(val):
        return True
    return str(val).strip().lower() in NA_TOKENS

def norm_text(val):
    return str(val).strip() if pd.notna(val) else ""

def append_warning(existing, new):
    a, b = (existing or "").strip(), (new or "").strip()
    if not a: return b
    if not b: return a
    return f"{a}, {b}"

# ---------- 1️⃣ Solution Deployed Date ----------
def process_solution_deployed_date(df):
    cols = [c for c in df.columns if c.startswith("Solution Deployed Date")]
    if not cols:
        return pd.DataFrame({
            "Final Solution Deployed Date":[pd.NA]*len(df),
            "Warnings_Date":[""]*len(df)
        })

    df_dates = df[cols].apply(pd.to_datetime, errors="coerce")
    finals, warns = [], []

    for _, row in df_dates.iterrows():
        valid = [d for d in row.values if pd.notna(d)]
        if not valid:
            finals.append(pd.NA); warns.append("")
        elif len(set(valid)) == 1:
            finals.append(min(valid)); warns.append("")
        else:
            finals.append(min(valid))
            warns.append("Multiple Solution Deployed Dates in upstream data")

    formatted = pd.Series(pd.to_datetime(finals, errors="coerce")).dt.strftime("%m/%d/%Y")
    return pd.DataFrame({
        "Final Solution Deployed Date": formatted,
        "Warnings_Date": warns
    })

# ---------- 2️⃣ Process Execution Location ----------
def process_execution_location(df):
    cols = [c for c in df.columns if c.startswith("Process Execution Location")]
    if not cols:
        return pd.DataFrame({
            "Final Process Execution Location":[pd.NA]*len(df),
            "Warnings_Location":[""]*len(df)
        })

    def normalized(v):
        return None if is_missing(v) else norm_text(v)

    finals, warns = [], []
    for _, row in df.iterrows():
        vals = [normalized(row[c]) for c in cols if normalized(row[c])]
        if not vals:
            finals.append(pd.NA); warns.append("")
        elif len({v.lower() for v in vals}) == 1:
            finals.append(vals[0]); warns.append("")
        else:
            finals.append(vals[0])
            warns.append("Multiple Process Execution Locations in upstream data")

    return pd.DataFrame({
        "Final Process Execution Location": finals,
        "Warnings_Location": warns
    })

# ---------- 3️⃣ Digital Tools (Consolidated + Reporting) ----------
def process_tools(df):
    tool_cols = [c for c in df.columns if str(c).strip().lower().startswith("what digital tools will be used")]
    bu_col  = next((c for c in df.columns if c.strip().lower()=="business unit"), None)
    div_col = next((c for c in df.columns if c.strip().lower()=="division"), None)
    idea_col= next((c for c in df.columns if c.strip().lower()=="idea type"), None)
    sol_col = next((c for c in df.columns if c.strip().lower()=="solution type"), None)
    date_col= next((c for c in df.columns if c.strip().lower() in {"date submitted","datesubmitted"}), None)

    if not tool_cols:
        return pd.DataFrame({
            "Expected Consolidated Tools":[pd.NA]*len(df),
            "Expected Tool for Reporting":[pd.NA]*len(df),
            "Warnings_Tools":[""]*len(df)
        })

    cons_list, tfr_list, warns = [], [], []
    placeholders = {"other","tbd","other/tbd"}

    def clean_token(tok):
        t = norm_text(tok)
        if "other process reengineering" in t.lower():
            return "Process Reengineering"
        if "other process decommission" in t.lower():
            return "Process Decommission"
        return t

    for _, row in df.iterrows():
        raw = [clean_token(row[c]) for c in tool_cols if not is_missing(row[c])]
        consolidated = "-".join(raw) if raw else pd.NA

        if isinstance(consolidated, str):
            text = consolidated.lower().strip().replace("–","-")
            if "other" in text and "process reengineering" in text:
                consolidated = "Process Reengineering"
            elif "other" in text and "process decommission" in text:
                consolidated = "Process Decommission"

        bu, div = norm_text(row.get(bu_col,"")), norm_text(row.get(div_col,""))
        idea, sol = norm_text(row.get(idea_col,"")), norm_text(row.get(sol_col,""))
        tfr = pd.NA

        # ---------- Step 2: Business Rules ----------
        if bu.lower() == "operations":
            if idea.lower() == "user-led" and sol.lower() == "process re-engineering":
                tfr = "Process Reengineering"
            elif idea.lower() == "user-led" and sol.lower() == "systemic enhancements":
                tfr = "System Enhancements"
            elif idea.lower() == "user-led" and sol.lower() == "tooling":
                tfr = consolidated
            elif idea.lower() == "pro-dev":
                tfr = consolidated
            elif idea.lower() == "core platform transformation":
                tfr = "Core Platform Transformation"
            else:
                tfr = consolidated

        elif bu.lower() == "company" and div.lower() == "finance":
            if idea.lower() == "new finance tactical automation" and sol.lower() == "systemic enhancements":
                tfr = consolidated
            elif idea.lower() == "new finance technology led solution":
                tfr = "Core Platform Transformation"
            else:
                tfr = consolidated

        elif bu.lower() == "business":
            if idea.lower() == "strategic transformation":
                tfr = "Core Platform Transformation"
            else:
                tfr = consolidated
        else:
            tfr = consolidated

        # ---------- Step 3: Consolidation Logic ----------
        toks = [t.strip() for t in str(consolidated).split("-") if t and not is_missing(t)]
        norm_toks = [t for t in toks if t.lower() not in placeholders]

        if pd.notna(tfr) and pd.notna(consolidated) and str(tfr) == str(consolidated):
            if len(norm_toks) == 0:
                tfr = pd.NA
            elif len(norm_toks) == 1:
                tfr = norm_toks[0]
            elif len(norm_toks) == 2:
                a,b = norm_toks; al,bl = a.lower(), b.lower()
                if ("process reengineering" in {al,bl}) and ("other" in {al,bl}):
                    tfr = "Process Reengineering"
                elif ("process reengineering" in {al,bl}) and not (al in placeholders or bl in placeholders):
                    tfr = b if al=="process reengineering" else a
                elif (al in placeholders or bl in placeholders):
                    tfr = b if al in placeholders else a
                else:
                    tfr = f"{a}-{b}"
            else:
                tfr = "Multiple"

        # ---------- Step 4: Fallback ----------
        if (pd.isna(tfr) or str(tfr).strip()==""):
            try:
                ds = pd.to_datetime(row.get(date_col), errors="coerce")
                if pd.notna(ds) and ds.year <= 2023 and (bu.lower()=="operations" or div.lower()=="finance"):
                    tfr = "UiPath"
            except:
                pass

        tfr = str(tfr).replace(",","-") if pd.notna(tfr) else pd.NA
        cons_list.append(consolidated)
        tfr_list.append(tfr)
        warns.append("")

    return pd.DataFrame({
        "Expected Consolidated Tools": cons_list,
        "Expected Tool for Reporting": tfr_list,
        "Warnings_Tools": warns
    })

# ---------- Combine All ----------
def merge_all(df):
    df1 = process_solution_deployed_date(df)
    df2 = process_execution_location(df)
    df3 = process_tools(df)
    combined = pd.concat([df, df1, df2, df3], axis=1)
    combined["Processing Warnings"] = ""
    for w in ["Warnings_Date","Warnings_Location","Warnings_Tools"]:
        if w in combined.columns:
            combined["Processing Warnings"] = [
                append_warning(a,b) for a,b in zip(combined["Processing Warnings"], combined[w].fillna(""))
            ]
    combined.drop(columns=["Warnings_Date","Warnings_Location","Warnings_Tools"], inplace=True, errors="ignore")
    tail = ["Final Solution Deployed Date","Final Process Execution Location",
            "Expected Consolidated Tools","Expected Tool for Reporting","Processing Warnings"]
    return combined[[c for c in combined.columns if c not in tail]+tail]

# ---------- Streamlit UI ----------
st.set_page_config(page_title="Process Data Portal", layout="wide")
st.title("📊 Process Optimization Data Processor-main 1")
st.markdown("Upload an **Excel or CSV** file to automatically derive all computed fields and warnings.")

uploaded_file = st.file_uploader("Upload your file", type=["xlsx","csv"])

if uploaded_file:
    df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith(".xlsx") else pd.read_csv(uploaded_file)
    st.success(f"✅ File loaded successfully: {df.shape[0]} rows, {df.shape[1]} columns")
    df_out = merge_all(df)
    st.dataframe(df_out.head(25))

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_out.to_excel(writer, index=False)
    buffer.seek(0)

    st.download_button(
        label="📥 Download Processed Excel",
        data=buffer,
        file_name="processed_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
