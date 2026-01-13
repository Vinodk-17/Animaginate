import re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Add Fleet Name to CSV", layout="centered")
st.title("Add Fleet Name using Fleet GUID (CSV → CSV)")

fleet_file = st.file_uploader(
    "Upload Fleet CSV (must have: fleet_guid, fleet_name)",
    type=["csv"]
)

target_file = st.file_uploader(
    "Upload Target CSV (must have: fleet_guid)",
    type=["csv"]
)

def read_csv(file):
    return pd.read_csv(file, dtype=str, encoding_errors="ignore")

def normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    return df

def make_join_key(x) -> str:
    # TEMP join key only for matching; original data stays untouched
    if pd.isna(x):
        return ""
    s = str(x).strip().lower()
    return re.sub(r"[^a-z0-9]", "", s)

if fleet_file and target_file:
    fleet_df = normalize_cols(read_csv(fleet_file))
    target_df = normalize_cols(read_csv(target_file))

    # Validate required columns
    if "fleet_guid" not in fleet_df.columns or "fleet_name" not in fleet_df.columns:
        st.error("Fleet CSV must contain columns: fleet_guid, fleet_name")
        st.stop()

    if "fleet_guid" not in target_df.columns:
        st.error("Target CSV must contain column: fleet_guid")
        st.stop()

    # TEMP join keys (do NOT modify original values)
    fleet_df["_join_key"] = fleet_df["fleet_guid"].apply(make_join_key)
    target_df["_join_key"] = target_df["fleet_guid"].apply(make_join_key)

    # LEFT JOIN: keep all target rows, add fleet_name where match exists
    merged_df = target_df.merge(
        fleet_df[["_join_key", "fleet_name"]],
        on="_join_key",
        how="left"
    )

    # Remove temp key from final output
    merged_df = merged_df.drop(columns=["_join_key"])

    st.subheader("Preview (fleet_name added)")
    st.write(f"Input rows: {len(target_df)} | Output rows: {len(merged_df)}")
    st.dataframe(merged_df, use_container_width=True)

    missing = merged_df["fleet_name"].isna().sum()
    st.info(f"Rows without fleet match (fleet_name blank): {missing}")

    # Output filename SAME as second input file
    output_filename = target_file.name

    csv_bytes = merged_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        label="Download Updated CSV",
        data=csv_bytes,
        file_name=output_filename,
        mime="text/csv"
    )
else:
    st.info("Upload both CSV files to add fleet_name and download the updated CSV.")
    
