import pandas as pd
import requests
import msal

# ================== CONFIG SECTION ==================

TENANT_ID = "YOUR_TENANT_ID"
CLIENT_ID = "YOUR_CLIENT_ID"
CLIENT_SECRET = "YOUR_CLIENT_SECRET"

# Your Dataverse environment URL (no trailing slash)
DATAVERSE_URL = "https://YOURORG.crm.dynamics.com"

# Entity set (table) name used by Web API (plural logical name)
# Example: "accounts", "new_movies", "crb_projects"
TABLE_ENTITY_SET = "YOUR_TABLE_ENTITY_SET_NAME"

# Full path to your Excel file (created by your other script)
EXCEL_PATH = r"C:\path\to\your\file.xlsx"

# Excel column name that holds Dataverse row ID (GUID) if you want to UPDATE
# Leave as None if you only want to CREATE new rows.
DATAVERSE_ID_COLUMN = "dataverse_id"   # or None

# Map Excel columns -> Dataverse column logical names
# Left side = Dataverse column schema name
# Right side = Excel column name
COLUMN_MAPPING = {
    # "schema_name_in_dataverse": "ColumnNameInExcel"
    "new_name": "Name",
    "new_description": "Description",
    "new_amount": "Amount",
    # Add more mappings here...
}

# ================== AUTH TOKEN FUNCTION ==================

def get_access_token():
    authority = f"https://login.microsoftonline.com/{TENANT_ID}"
    scope = [f"{DATAVERSE_URL}/.default"]

    app = msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=authority,
        client_credential=CLIENT_SECRET
    )

    result = app.acquire_token_for_client(scopes=scope)

    if "access_token" not in result:
        raise Exception(f"Failed to acquire token: {result}")

    return result["access_token"]

# ================== MAIN UPLOAD LOGIC ==================

def build_record_from_row(row):
    """
    Convert one row from Excel into a Dataverse JSON payload
    using COLUMN_MAPPING.
    """
    data = {}
    for dv_col, xls_col in COLUMN_MAPPING.items():
        if xls_col in row and pd.notna(row[xls_col]):
            data[dv_col] = row[xls_col]
    return data


def create_record(headers, payload):
    url = f"{DATAVERSE_URL}/api/data/v9.2/{TABLE_ENTITY_SET}"
    response = requests.post(url, headers=headers, json=payload)

    if response.status_code in (200, 201, 204):
        print("Created record successfully")
    else:
        print("Create failed:", response.status_code, response.text)


def update_record(headers, record_id, payload):
    # record_id must be GUID without braces {}
    url = f"{DATAVERSE_URL}/api/data/v9.2/{TABLE_ENTITY_SET}({record_id})"
    response = requests.patch(url, headers=headers, json=payload)

    if response.status_code in (200, 204):
        print(f"Updated record {record_id} successfully")
    else:
        print(f"Update failed for {record_id}:", response.status_code, response.text)


def main():
    # 1. Get token
    token = get_access_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0",
        "Accept": "application/json"
    }

    # 2. Load Excel
    df = pd.read_excel(EXCEL_PATH)

    # 3. Loop rows
    for idx, row in df.iterrows():
        payload = build_record_from_row(row)

        if not payload:
            print(f"Row {idx}: No mapped data, skipping")
            continue

        if DATAVERSE_ID_COLUMN and DATAVERSE_ID_COLUMN in df.columns and pd.notna(row[DATAVERSE_ID_COLUMN]):
            # UPDATE existing record
            record_id = str(row[DATAVERSE_ID_COLUMN]).strip().replace("{", "").replace("}", "")
            print(f"Row {idx}: Updating {record_id}")
            update_record(headers, record_id, payload)
        else:
            # CREATE new record
            print(f"Row {idx}: Creating new record")
            create_record(headers, payload)


if __name__ == "__main__":
    main()
