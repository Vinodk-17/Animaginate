import io
import re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Fleet + Squad Merge", layout="centered")
st.title("Merge Two Excels (Original Data As-Is)")

fleet_file = st.file_uploader("Upload Fleet Excel (fleet_guid, fleet_name)", type=["xlsx"])
squad_file = st.file_uploader("Upload Squad Excel (squad_guid, squad_name, fleet_guid)", type=["xlsx"])

def norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    return df

def make_join_key(x) -> str:
    """
    TEMP key only for matching:
    - lower + strip
    - remove non-alphanumeric (special chars)
    Original column values are NOT changed.
    """
    if pd.isna(x):
        return ""
    s = str(x).strip().lower()
    return re.sub(r"[^a-z0-9]", "", s)

if fleet_file and squad_file:
    fleet_xls = pd.ExcelFile(fleet_file)
    squad_xls = pd.ExcelFile(squad_file)

    fleet_sheet = st.selectbox("Fleet file sheet", fleet_xls.sheet_names, index=0)
    squad_sheet = st.selectbox("Squad file sheet", squad_xls.sheet_names, index=0)

    fleet_df = pd.read_excel(fleet_file, sheet_name=fleet_sheet, dtype=str)
    squad_df = pd.read_excel(squad_file, sheet_name=squad_sheet, dtype=str)

    fleet_df = norm_cols(fleet_df)
    squad_df = norm_cols(squad_df)

    # Validate required columns
    need_fleet = {"fleet_guid", "fleet_name"}
    need_squad = {"squad_guid", "squad_name", "fleet_guid"}

    mf = need_fleet - set(fleet_df.columns)
    ms = need_squad - set(squad_df.columns)

    if mf:
        st.error(f"Fleet file missing columns: {mf}")
        st.stop()
    if ms:
        st.error(f"Squad file missing columns: {ms}")
        st.stop()

    # TEMP join keys (original data stays untouched)
    fleet_df["_join_key"] = fleet_df["fleet_guid"].apply(make_join_key)
    squad_df["_join_key"] = squad_df["fleet_guid"].apply(make_join_key)

    # Merge: keep all squad rows, attach fleet_name
    merged_df = squad_df.merge(
        fleet_df[["_join_key", "fleet_name"]],
        on="_join_key",
        how="left"
    )

    # Drop temp key from final output (so data stays "as it is")
    merged_df = merged_df.drop(columns=["_join_key"])

    st.subheader("Preview (Merged)")
    st.dataframe(merged_df, use_container_width=True)

    # Unmatched rows (optional)
    unmatched = merged_df[merged_df["fleet_name"].isna()]
    if not unmatched.empty:
        st.warning(f"{len(unmatched)} rows not matched (fleet_name missing).")
        with st.expander("Show unmatched rows"):
            st.dataframe(unmatched, use_container_width=True)

    # Export Excel to download
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        fleet_df.drop(columns=["_join_key"]).to_excel(writer, sheet_name="fleet_master", index=False)
        squad_df.drop(columns=["_join_key"]).to_excel(writer, sheet_name="squad_master", index=False)
        merged_df.to_excel(writer, sheet_name="merged", index=False)
        if not unmatched.empty:
            unmatched.to_excel(writer, sheet_name="unmatched", index=False)

    st.download_button(
        "Download Final Excel",
        data=output.getvalue(),
        file_name="fleet_squad_merged.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.info("Upload both Excel files to merge.")
