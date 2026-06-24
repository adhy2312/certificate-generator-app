import re
import pandas as pd
from io import BytesIO
from urllib.parse import urlparse

# Allowlist: only fetch from Google Sheets to prevent SSRF attacks
_ALLOWED_FETCH_DOMAIN = "docs.google.com"

def parse_google_sheet_url(url: str) -> str:
    """Extracts Spreadsheet ID and GID, returns a forced CSV export URL."""
    # SSRF guard: ensure the URL is actually a Google Sheets URL before parsing
    try:
        parsed = urlparse(url.strip())
        if parsed.netloc != _ALLOWED_FETCH_DOMAIN:
            raise ValueError("Only Google Sheets URLs are accepted.")
    except Exception:
        return ""

    match = re.search(r'/d/([a-zA-Z0-9-_]+)', url)
    if not match:
        return ""
    spreadsheet_id = match.group(1)

    gid_match = re.search(r'[#&]gid=([0-9]+)', url)
    gid = gid_match.group(1) if gid_match else "0"

    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={gid}"

def process_source(file_data=None, url=None) -> list:
    """Parses incoming spreadsheet data using Pandas."""
    df = pd.DataFrame()
    try:
        if url:
            if not isinstance(url, str) or not url.strip():
                raise ValueError("Empty or invalid URL provided.")
            export_url = parse_google_sheet_url(url)
            if not export_url:
                raise ValueError("Could not parse a valid Google Sheets URL.")
            df = pd.read_csv(export_url)
        elif file_data:
            # Check filename extension if available, else try pandas read_csv/read_excel
            try:
                df = pd.read_csv(BytesIO(file_data))
            except Exception:
                df = pd.read_excel(BytesIO(file_data), engine='openpyxl')
        else:
            raise ValueError("No data source provided.")
                
        # Normalize headers (strip whitespace and title case)
        df.columns = df.columns.str.strip().str.title()
        
        # Fuzzy match common column names
        column_mapping = {}
        for col in df.columns:
            lower_col = col.lower()
            if "email" in lower_col:
                column_mapping[col] = "Email"
            elif "name" in lower_col and "event" not in lower_col:
                column_mapping[col] = "Name"
        
        df.rename(columns=column_mapping, inplace=True)
        
        # Validation
        required_cols = ['Name', 'Email']
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(missing)}. Please ensure your sheet has Name and Email columns.")
            
        # Add default Tier if missing (since you don't need Winner/Resource Person in bulk)
        if 'Tier' not in df.columns:
            df['Tier'] = 'Participant'
            
        return df.to_dict(orient='records')
    except Exception as e:
        raise Exception(f"Data ingestion error: {e}")
