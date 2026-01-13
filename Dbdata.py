import io
import re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="CSV Merge → Excel", layout="centered")
st.title("Merge 2 CSVs (Fleet + Squad) → Download Excel")

fleet_file = st.file_uploader("Upload Fleet CSV (fleet_guid, fleet_name)", type=["csv"])
squad_file = st.file_uploader("Upload Squad CSV (squad_guid, squad_name, fleet_guid)", type=["csv"])

def norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    return df

def make_join_key(x) -> str:
    # TEMP key only for matching; original data stays untouched
    if pd.isna(x):
        return ""
    s = str(x).strip().lower()
    return re.sub(r"[^a-z0-9]", "", s)

def read_csv(uploaded_file) -> pd.DataFrame:
    # dtype=str keeps GUIDs safe (no scientific notation)
    return pd.read_csv(uploaded_file, dtype=str, encoding_errors="ignore")

if fleet_file and squad_file:
    fleet_df = norm_cols(read_csv(fleet_file))
    squad_df = norm_cols(read_csv(squad_file))

    # Required columns check
    need_fleet = {"fleet_guid", "fleet_name"}
    need_squad = {"squad_guid", "squad_name", "fleet_guid"}

    mf = need_fleet - set(fleet_df.columns)
    ms = need_squad - set(squad_df.columns)

    if mf:
        st.error(f"Fleet CSV missing columns: {mf}")
        st.stop()
    if ms:
        st.error(f"Squad CSV missing columns: {ms}")
        st.stop()

    # Temporary join keys (do NOT modify original fleet_guid values)
    fleet_df["_join_key"] = fleet_df["fleet_guid"].apply(make_join_key)
    squad_df["_join_key"] = squad_df["fleet_guid"].apply(make_join_key)

    # Merge: keep all squad rows, add fleet_name
    merged_df = squad_df.merge(
        fleet_df[["_join_key", "fleet_name"]],
        on="_join_key",
        how="left"
    )

    # Remove temp key from final output to keep data "as it is"
    merged_df = merged_df.drop(columns=["_join_key"])

    st.subheader("Merged Preview")
    st.dataframe(merged_df, use_container_width=True)

    unmatched = merged_df[merged_df["fleet_name"].isna()]
    if not unmatched.empty:
        st.warning(f"{len(unmatched)} rows not matched (fleet_name missing).")
        with st.expander("Show unmatched"):
            st.dataframe(unmatched, use_container_width=True)

    # Create Excel output in memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        fleet_df.drop(columns=["_join_key"]).to_excel(writer, sheet_name="fleet_master", index=False)
        squad_df.drop(columns=["_join_key"]).to_excel(writer, sheet_name="squad_master", index=False)
        merged_df.to_excel(writer, sheet_name="merged", index=False)
        if not unmatched.empty:
            unmatched.to_excel(writer, sheet_name="unmatched", index=False)

    st.download_button(
        "Download Excel Output",
        data=output.getvalue(),
        file_name="fleet_squad_merged.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
else:
    st.info("Upload both CSV files to merge and download Excel.")
    
