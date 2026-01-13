import re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Add Squad Name + Fleet Name", layout="centered")
st.title("Add squad_name + fleet_name using squad_guid (CSV → CSV)")

master_file = st.file_uploader(
    "Upload Master Squad CSV (must have: squad_guid, squad_name, fleet_name)",
    type=["csv"]
)

target_file = st.file_uploader(
    "Upload Target CSV (must have: squad_guid only)",
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

if master_file and target_file:
    master_df = normalize_cols(read_csv(master_file))
    target_df = normalize_cols(read_csv(target_file))

    # Accept either "squid_guid" typo or correct "squad_guid" in target
    guid_col = None
    if "squad_guid" in target_df.columns:
        guid_col = "squad_guid"
    elif "squid_guid" in target_df.columns:
        guid_col = "squid_guid"
    else:
        st.error("Target CSV must contain: squad_guid (or squid_guid)")
        st.stop()

    # Master must contain these
    required_master = {"squad_guid", "squad_name", "fleet_name"}
    missing_master = required_master - set(master_df.columns)
    if missing_master:
        st.error(f"Master CSV missing columns: {missing_master}")
        st.stop()

    # TEMP join keys
    master_df["_join_key"] = master_df["squad_guid"].apply(make_join_key)
    target_df["_join_key"] = target_df[guid_col].apply(make_join_key)

    # LEFT JOIN: keep all target rows, attach names
    merged_df = target_df.merge(
        master_df[["_join_key", "squad_name", "fleet_name"]],
        on="_join_key",
        how="left"
    )

    # Build final output with required columns only
    final_df = pd.DataFrame({
        "squad_guid": merged_df[guid_col],          # keep original value from target
        "squad_name": merged_df["squad_name"],
        "fleet_name": merged_df["fleet_name"]
    })

    st.subheader("Preview (Final Output)")
    st.write(f"Input rows: {len(target_df)} | Output rows: {len(final_df)}")
    st.dataframe(final_df, use_container_width=True)

    missing = final_df["squad_name"].isna().sum()
    st.info(f"Rows without squad match (squad_name/fleet_name blank): {missing}")

    # Output file name same as target (second input file)
    output_filename = target_file.name

    csv_bytes = final_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download Final CSV",
        data=csv_bytes,
        file_name=output_filename,
        mime="text/csv"
    )

else:
    st.info("Upload both CSV files to generate the final CSV.")
  
