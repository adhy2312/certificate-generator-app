import re
import requests
import pandas as pd
from io import BytesIO
from urllib.parse import urlparse

# Allowlist: only fetch from Google Sheets to prevent SSRF attacks
_ALLOWED_FETCH_DOMAIN = "docs.google.com"

def parse_google_sheet_url(url: str) -> str:
    """Extracts Spreadsheet ID and GID, returns a forced CSV export URL."""
    try:
        parsed = urlparse(url.strip())
        if parsed.netloc != _ALLOWED_FETCH_DOMAIN:
            raise ValueError("Only Google Sheets URLs are accepted.")
    except Exception:
        return ""

    # Check for "published to web" links
    if "/d/e/" in url:
        match = re.search(r'/d/e/([a-zA-Z0-9-_]+)', url)
        if match:
            return f"https://docs.google.com/spreadsheets/d/e/{match.group(1)}/pub?output=csv"
            
    match = re.search(r'/d/([a-zA-Z0-9-_]+)', url)
    if not match:
        return ""
    spreadsheet_id = match.group(1)

    gid_match = re.search(r'[#&]gid=([0-9]+)', url)
    gid = gid_match.group(1) if gid_match else "0"

    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&id={spreadsheet_id}&gid={gid}"

def process_source(file_data=None, url=None) -> list:
    """Parses incoming spreadsheet data using Pandas with high resilience."""
    df = pd.DataFrame()
    try:
        if url:
            if not isinstance(url, str) or not url.strip():
                raise ValueError("Empty or invalid URL provided.")
            export_url = parse_google_sheet_url(url)
            if not export_url:
                raise ValueError("Could not parse a valid Google Sheets URL. Please check the link.")
            
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ISTE-CertHub/2.0"}
                resp = requests.get(export_url, headers=headers, timeout=20)
                if resp.status_code == 404:
                    raise ValueError("Google Sheet not found. Please verify the link.")
                if resp.status_code == 400 or "ServiceLogin" in resp.text:
                    raise ValueError("Google Sheet is private. Please ensure link sharing is set to 'Anyone with the link can view'.")
                resp.raise_for_status()
                df = pd.read_csv(BytesIO(resp.content))
            except requests.Timeout:
                raise ValueError("Google Sheets server timed out. Please retry or download as CSV and upload directly.")
            except Exception as read_err:
                if "400" in str(read_err) or "404" in str(read_err):
                    raise ValueError("Google blocked the request. Please ensure the sheet is set to 'Anyone with the link can view'.")
                raise read_err
        elif file_data:
            try:
                df = pd.read_csv(BytesIO(file_data))
            except Exception:
                df = pd.read_excel(BytesIO(file_data), engine='openpyxl')
        else:
            raise ValueError("No data source provided.")

        # Strip whitespace from column headers
        df.columns = df.columns.astype(str).str.strip()
        
        # Fuzzy match common column names
        column_mapping = {}
        found_email = False
        found_name = False
        found_tier = False
        found_type = False
        
        for col in df.columns:
            lower_col = col.lower()
            if not found_email and ("email" in lower_col or "e-mail" in lower_col or "mail id" in lower_col):
                column_mapping[col] = "Email"
                found_email = True
            elif not found_name and ("name" in lower_col or "participant" in lower_col or "student" in lower_col) and "event" not in lower_col and "school" not in lower_col and "college" not in lower_col:
                column_mapping[col] = "Name"
                found_name = True
            elif not found_tier and ("tier" in lower_col or "role" in lower_col or "prize" in lower_col or "category" in lower_col or "position" in lower_col):
                column_mapping[col] = "Tier"
                found_tier = True
            elif not found_type and ("cert_type" in lower_col or "certificate type" in lower_col or lower_col == "type"):
                column_mapping[col] = "Type"
                found_type = True
        
        df.rename(columns=column_mapping, inplace=True)
        df = df.loc[:, ~df.columns.duplicated()]
        
        # Validation
        required_cols = ['Name', 'Email']
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(missing)}. Detected columns: {', '.join(df.columns)}")
            
        if 'Tier' not in df.columns:
            df['Tier'] = 'Participant'
        if 'Type' not in df.columns:
            df['Type'] = ''
            
        # 1. Name Formatting
        df['Name'] = df['Name'].astype(str).str.strip().str.title()
        
        # 2. Email Validation & Cleanup
        email_pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        df['Email'] = df['Email'].astype(str).str.strip()
        df = df[df['Email'].str.match(email_pattern, na=False)]
        
        if df.empty:
            raise ValueError("No valid records found. All rows contained invalid or missing email addresses.")
            
        # 3. Smart Deduplication
        df = df.drop_duplicates(subset=['Email'], keep='first')
        
        # 4. Fill NaN values cleanly
        df = df.fillna("")
        
        return df.to_dict(orient='records')
    except Exception as e:
        raise Exception(f"Data ingestion error: {e}")
