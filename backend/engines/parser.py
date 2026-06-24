import re
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
            # Published to web CSV export format
            return f"https://docs.google.com/spreadsheets/d/e/{match.group(1)}/pub?output=csv"
            
    match = re.search(r'/d/([a-zA-Z0-9-_]+)', url)
    if not match:
        return ""
    spreadsheet_id = match.group(1)

    gid_match = re.search(r'[#&]gid=([0-9]+)', url)
    gid = gid_match.group(1) if gid_match else "0"

    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&id={spreadsheet_id}&gid={gid}"

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
            
            try:
                df = pd.read_csv(export_url)
            except Exception as read_err:
                if "400" in str(read_err) or "404" in str(read_err):
                    raise ValueError("Google blocked the request. Please ensure the sheet is set to 'Anyone with the link can view'.")
                else:
                    raise read_err
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
        
        # Fuzzy match common column names (only match the FIRST occurrence to prevent duplicate columns)
        column_mapping = {}
        found_email = False
        found_name = False
        
        for col in df.columns:
            lower_col = col.lower()
            if not found_email and "email" in lower_col:
                column_mapping[col] = "Email"
                found_email = True
            elif not found_name and "name" in lower_col and "event" not in lower_col and "school" not in lower_col and "college" not in lower_col:
                column_mapping[col] = "Name"
                found_name = True
        
        df.rename(columns=column_mapping, inplace=True)
        
        # Strip any duplicate columns just in case
        df = df.loc[:, ~df.columns.duplicated()]
        
        # Validation
        required_cols = ['Name', 'Email']
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(missing)}. Please ensure your sheet has Name and Email columns.")
            
        # Add default Tier if missing (since you don't need Winner/Resource Person in bulk)
        if 'Tier' not in df.columns:
            df['Tier'] = 'Participant'
            
        # --- INTELLIGENT PROCESSING LAYER ---
        
        # 1. Name Auto-Formatting (Strip outer whitespace and Title Case)
        df['Name'] = df['Name'].astype(str).str.strip().str.title()
        
        # 2. Invalid Email Bouncing (Filter out badly formed emails)
        email_pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        df['Email'] = df['Email'].astype(str).str.strip()
        df = df[df['Email'].str.match(email_pattern, na=False)]
        
        if df.empty:
            raise ValueError("No valid records found. All rows contained invalid or missing email addresses.")
            
        # 3. Smart Deduplication (Prevent spamming if user submitted form multiple times)
        df = df.drop_duplicates(subset=['Email'], keep='first')
        
        # 4. Fill NaN values (FastAPI's JSONResponse crashes on NaN)
        df = df.fillna("")
        
        return df.to_dict(orient='records')
    except Exception as e:
        raise Exception(f"Data ingestion error: {e}")
