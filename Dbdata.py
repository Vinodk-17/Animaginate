import re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="CSV Merge (Fleet + Squad)", layout="centered")
st.title("Merge 2 CSVs (Fleet + Squad) → Full Output CSV")

fleet_file = st.file_uploader("Upload Fleet CSV (fleet_guid, fleet_name)", type=["csv"])
squad_file = st.file_uploader("Upload Squad CSV (squad_guid, squad_name, fleet_guid)", type=["csv"])

def norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    return df

def make_join_key(x) -> str:
    # TEMP key for matching only; does NOT change original values
    if pd.isna(x):
        return ""
    s = str(x).strip().lower()
    return re.sub(r"[^a-z0-9]", "", s)

def read_csv(uploaded_file) -> pd.DataFrame:
    return pd.read_csv(uploaded_file, dtype=str, encoding_errors="ignore")

if fleet_file and squad_file:
    fleet_df = norm_cols(read_csv(fleet_file))
    squad_df = norm_cols(read_csv(squad_file))

    # Validate required columns
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

    # TEMP join keys
    fleet_df["_join_key"] = fleet_df["fleet_guid"].apply(make_join_key)
    squad_df["_join_key"] = squad_df["fleet_guid"].apply(make_join_key)

    # ✅ LEFT JOIN ensures ALL squad rows remain
    merged_df = squad_df.merge(
        fleet_df[["_join_key", "fleet_name"]],
        on="_join_key",
        how="left"   # IMPORTANT
    )

    # Remove temp key from final output
    merged_df = merged_df.drop(columns=["_join_key"])

    st.subheader("Preview: Full Output (All Squad Rows)")
    st.write(f"Squad input rows: {len(squad_df)} | Output rows: {len(merged_df)}")
    st.dataframe(merged_df, use_container_width=True)

    # Just show count of missing matches (optional)
    missing_count = merged_df["fleet_name"].isna().sum()
    st.info(f"Rows with no fleet match (fleet_name blank): {missing_count}")

    # Download FULL merged CSV
    csv_bytes = merged_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download FULL Merged CSV",
        data=csv_bytes,
        file_name="full_merged_output.csv",
        mime="text/csv"
    )
else:
    st.info("Upload both CSV files to merge.")
    
