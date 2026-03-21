#!/usr/bin/env python3
"""
Standalone Google Sheets Setup Utility for ApexBT.

This script creates and configures Google Sheets spreadsheets without
requiring the full application config (no DB, Twitter, etc. needed).

Credentials are loaded in this order:
  1. Local JSON file  – set CREDENTIALS_FILE below, or pass --creds <path>
  2. AWS Secrets Manager – using the 'apexbt' profile

Usage:
    python setup_sheets.py                       # tries local file, then AWS
    python setup_sheets.py --creds creds.json    # use a specific JSON file
"""

import os
import sys
import json
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime, timedelta

import gspread
from oauth2client.service_account import ServiceAccountCredentials

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration – edit these if needed
# ---------------------------------------------------------------------------
AWS_REGION = "us-east-1"
AWS_PROFILE = "apexbt"
SHEETS_SECRET_NAME = "GOOGLE_SHEETS_CREDENTIALS"

# If you have the service-account JSON file locally, set its path here.
# You can also pass --creds <path> on the command line to override.
CREDENTIALS_FILE = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_FILE", "")

SPREADSHEET_NAME = "ApeXBT"
HISTORICAL_SPREADSHEET_NAME = "ApexBT Historical Data"

# The email address that should be granted write access to new sheets
OWNER_EMAIL = "yhp2378@gmail.com"

# ---------------------------------------------------------------------------
# Rate limiter (Google Sheets API has 60 req/min quota)
# ---------------------------------------------------------------------------

class RateLimiter:
    def __init__(self, max_requests_per_minute: int = 50):
        self.max_requests = max_requests_per_minute
        self.requests: list[datetime] = []

    def wait_if_needed(self) -> None:
        now = datetime.now()
        cutoff = now - timedelta(minutes=1)
        self.requests = [t for t in self.requests if t > cutoff]

        if len(self.requests) >= self.max_requests:
            sleep_time = (self.requests[0] + timedelta(minutes=1) - now).total_seconds()
            if sleep_time > 0:
                logger.info(f"Rate limit reached, waiting {sleep_time:.1f}s …")
                time.sleep(sleep_time)

        self.requests.append(datetime.now())


rate_limiter = RateLimiter()

# ---------------------------------------------------------------------------
# Credential loading (local file first, then AWS fallback)
# ---------------------------------------------------------------------------

def _load_from_file(path: str) -> dict | None:
    """Try to load service-account JSON from a local file."""
    p = Path(path).expanduser()
    if not p.is_file():
        return None
    try:
        with open(p) as f:
            creds = json.load(f)
        if "client_email" in creds:
            logger.info(f"Loaded credentials from local file: {p}")
            return creds
        logger.warning(f"File {p} does not look like a service-account JSON (missing 'client_email')")
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"Could not read {p}: {exc}")
    return None


def _load_from_aws() -> dict | None:
    """Try to load service-account JSON from AWS Secrets Manager."""
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        logger.warning("boto3 is not installed – skipping AWS Secrets Manager")
        return None

    try:
        session = boto3.Session(profile_name=AWS_PROFILE)
        client = session.client("secretsmanager", region_name=AWS_REGION)
        response = client.get_secret_value(SecretId=SHEETS_SECRET_NAME)
        secret = json.loads(response["SecretString"])
        logger.info("Loaded credentials from AWS Secrets Manager")
        return secret
    except ClientError as exc:
        logger.warning(f"AWS error retrieving '{SHEETS_SECRET_NAME}': {exc}")
    except Exception as exc:
        logger.warning(f"Unexpected AWS error: {exc}")
    return None


def get_sheets_credentials(cli_creds_path: str | None = None) -> dict:
    """
    Load Google Sheets service-account credentials.

    Resolution order:
      1. Explicit path passed via --creds CLI arg
      2. CREDENTIALS_FILE config / GOOGLE_SHEETS_CREDENTIALS_FILE env var
      3. Common local filenames (credentials.json, service_account.json, etc.)
      4. AWS Secrets Manager
    """
    # 1. Explicit CLI path
    if cli_creds_path:
        creds = _load_from_file(cli_creds_path)
        if creds:
            return creds
        logger.error(f"Could not load credentials from specified path: {cli_creds_path}")
        raise FileNotFoundError(f"Credentials file not found or invalid: {cli_creds_path}")

    # 2. Config / env var path
    if CREDENTIALS_FILE:
        creds = _load_from_file(CREDENTIALS_FILE)
        if creds:
            return creds

    # 3. Common local filenames
    common_names = [
        "credentials.json",
        "service_account.json",
        "google_credentials.json",
        "sheets_credentials.json",
        "google_sheets_credentials.json",
    ]
    for name in common_names:
        creds = _load_from_file(name)
        if creds:
            return creds

    # 4. AWS fallback
    creds = _load_from_aws()
    if creds:
        return creds

    raise RuntimeError(
        "Could not load Google Sheets credentials from any source.\n"
        "Either:\n"
        "  • Place your service-account JSON file in the current directory\n"
        "    (e.g. credentials.json, service_account.json)\n"
        "  • Pass --creds <path> on the command line\n"
        "  • Set GOOGLE_SHEETS_CREDENTIALS_FILE env var\n"
        "  • Configure AWS profile 'apexbt' with valid credentials"
    )


def authorize_gspread(credentials_dict: dict) -> gspread.Client:
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
    return gspread.authorize(creds)

# ---------------------------------------------------------------------------
# Worksheet header definitions
# ---------------------------------------------------------------------------

TWEETS_HEADERS = [
    "Tweet ID",
    "AI Agent",
    "Text",
    "Created At",
    "Timestamp",
    "Ticker",
    "Ticker Status",
    "Current Price USD",
    "Tweet Time Price USD",
    "Volume 24h",
    "Liquidity",
    "Price Change 24h %",
    "DEX",
    "Network",
    "Trading Pair",
    "Contract Address",
    "Last Updated",
]

TRADES_HEADERS = [
    "Trade ID",
    "AI Agent",
    "Timestamp",
    "Ticker",
    "Contract Address",
    "Network",
    "Entry Price",
    "Position Size",
    "Direction",
    "Stop Loss",
    "Take Profit",
    "Tweet ID Reference",
    "Status",
    "Exit Price",
    "Exit Timestamp",
    "PNL Amount",
    "PNL Percentage",
    "ATH Price",
    "ATH Timestamp",
    "Market Cap",
    "Notes",
]

PNL_HEADERS = [
    "AI Agent",
    "Ticker",
    "Contract Address",
    "Entry Time",
    "Entry Price",
    "Current Price",
    "ATH Price",
    "ATH Time",
    "Stop Loss",
    "Price Change %",
    "From ATH %",
    "To Stop Loss %",
    "Invested Amount ($)",
    "Current Value ($)",
    "PNL ($)",
]

AGENT_SUMMARY_HEADERS = [
    "Agent Name",
    "Total Tweets",
    "Single Ticker Tweets",
    "Qualified Tweets",
    "Total PNL ($)",
    "Closed Trades PNL ($)",
    "Open Trades PNL ($)",
    "Total Trades",
    "Closed Trades",
    "Open Trades",
    "Overall Win Rate (%)",
    "Closed Win Rate (%)",
    "Open Win Rate (%)",
    "Best Trade",
    "Worst Trade",
    "Last Updated",
]

SUMMARY_HEADERS = ["Metric", "Value"]

ACCOUNTS_HEADERS = ["Twitter Handle"]

# Mapping: worksheet name -> (headers, rows, cols)
WORKSHEET_SPECS = {
    "Tweets":       (TWEETS_HEADERS,        1000, 20),
    "Trades":       (TRADES_HEADERS,        1000, 25),
    "PNL":          (PNL_HEADERS,           1000, 15),
    "AgentSummary": (AGENT_SUMMARY_HEADERS, 100,  20),
    "Summary":      (SUMMARY_HEADERS,       20,   2),
    "Accounts":     (ACCOUNTS_HEADERS,      100,  1),
}

# ---------------------------------------------------------------------------
# Sheet setup helpers
# ---------------------------------------------------------------------------

def ensure_worksheet(spreadsheet: gspread.Spreadsheet, name: str, rows: int, cols: int) -> gspread.Worksheet:
    """Get existing worksheet or create a new one."""
    rate_limiter.wait_if_needed()
    try:
        ws = spreadsheet.worksheet(name)
        logger.info(f"  Found existing worksheet: {name}")
        return ws
    except gspread.exceptions.WorksheetNotFound:
        pass

    # If this is the very first worksheet, rename Sheet1 instead of adding
    rate_limiter.wait_if_needed()
    try:
        sheet1 = spreadsheet.sheet1
        if sheet1.title == "Sheet1":
            sheet1.update_title(name)
            logger.info(f"  Renamed 'Sheet1' → '{name}'")
            return sheet1
    except Exception:
        pass

    rate_limiter.wait_if_needed()
    ws = spreadsheet.add_worksheet(name, rows, cols)
    logger.info(f"  Created worksheet: {name}")
    return ws


def set_headers(ws: gspread.Worksheet, headers: list[str]) -> None:
    """Write headers to row 1 if they are missing or different."""
    rate_limiter.wait_if_needed()
    existing = ws.get_all_values()
    if existing and existing[0] == headers:
        logger.info(f"  Headers already correct on '{ws.title}'")
        return

    if existing:
        rate_limiter.wait_if_needed()
        ws.clear()
        logger.info(f"  Cleared old data on '{ws.title}'")

    rate_limiter.wait_if_needed()
    ws.append_row(headers)
    logger.info(f"  Wrote {len(headers)} headers to '{ws.title}'")


def setup_worksheets(spreadsheet: gspread.Spreadsheet, historical: bool = False) -> dict[str, gspread.Worksheet]:
    """Create / configure every worksheet in a spreadsheet."""
    suffix = "_Historical" if historical else ""
    sheets: dict[str, gspread.Worksheet] = {}

    for base_name, (headers, rows, cols) in WORKSHEET_SPECS.items():
        ws_name = f"{base_name}{suffix}"
        ws = ensure_worksheet(spreadsheet, ws_name, rows, cols)
        set_headers(ws, headers)
        sheets[base_name.lower()] = ws

    return sheets

# ---------------------------------------------------------------------------
# High-level actions
# ---------------------------------------------------------------------------

def list_service_account_files(gc: gspread.Client) -> list[dict]:
    """List all spreadsheets owned by the service account."""
    rate_limiter.wait_if_needed()
    return gc.list_spreadsheet_files()


def cleanup_service_account_drive(gc: gspread.Client) -> int:
    """Delete ALL spreadsheets from the service account's Drive to free quota."""
    files = list_service_account_files(gc)
    if not files:
        logger.info("Service account Drive is already empty.")
        return 0

    print(f"\nFound {len(files)} spreadsheet(s) on the service account's Drive:\n")
    for i, f in enumerate(files, 1):
        print(f"  {i}. {f['name']}  (ID: {f['id']})")

    print()
    confirm = input(f"Delete ALL {len(files)} file(s) to free up quota? [y/N]: ").strip().lower()
    if confirm not in ("y", "yes"):
        print("Skipped.")
        return 0

    deleted = 0
    for f in files:
        try:
            rate_limiter.wait_if_needed()
            gc.del_spreadsheet(f["id"])
            logger.info(f"  Deleted: {f['name']} ({f['id']})")
            deleted += 1
        except Exception as exc:
            logger.warning(f"  Could not delete {f['name']}: {exc}")

    print(f"\n🗑  Deleted {deleted}/{len(files)} file(s).\n")
    return deleted


def create_spreadsheet(gc: gspread.Client, historical: bool = False) -> str:
    """Create a new spreadsheet, set up worksheets, return its ID."""
    name = HISTORICAL_SPREADSHEET_NAME if historical else SPREADSHEET_NAME
    label = "historical " if historical else ""

    logger.info(f"Creating {label}spreadsheet: '{name}' …")
    try:
        sh = gc.create(name)
    except gspread.exceptions.APIError as exc:
        if "storageQuotaExceeded" in str(exc):
            print("\n⚠️  Service account Drive quota exceeded!")
            print("    Use option 7 to clean up old files, or option 8 to set up")
            print("    a sheet you created manually in your own Google Drive.\n")
            raise
        raise
    spreadsheet_id = sh.id
    logger.info(f"Created spreadsheet ID: {spreadsheet_id}")

    # Open by key so we're working with the actual object
    spreadsheet = gc.open_by_key(spreadsheet_id)

    logger.info("Setting up worksheets …")
    setup_worksheets(spreadsheet, historical=historical)

    # Clean up default 'Sheet1' if it still exists and isn't one of ours
    rate_limiter.wait_if_needed()
    try:
        sheet1 = spreadsheet.worksheet("Sheet1")
        spreadsheet.del_worksheet(sheet1)
        logger.info("  Removed leftover 'Sheet1'")
    except gspread.exceptions.WorksheetNotFound:
        pass

    return spreadsheet_id


def grant_access(gc: gspread.Client, spreadsheet_id: str, email: str) -> None:
    """Share the spreadsheet with the given email."""
    logger.info(f"Granting write access to {email} …")
    spreadsheet = gc.open_by_key(spreadsheet_id)
    spreadsheet.share(email, perm_type="user", role="writer")
    logger.info(f"Access granted!")
    print(f"\n✅  Open the spreadsheet at:")
    print(f"    https://docs.google.com/spreadsheets/d/{spreadsheet_id}\n")


def setup_existing_spreadsheet(gc: gspread.Client, name: str, historical: bool = False) -> None:
    """Open an existing spreadsheet by name and ensure worksheets + headers."""
    logger.info(f"Opening existing spreadsheet: '{name}' …")
    try:
        spreadsheet = gc.open(name)
    except gspread.exceptions.SpreadsheetNotFound:
        logger.error(f"Spreadsheet '{name}' not found. Create it first.")
        return

    logger.info("Setting up worksheets …")
    setup_worksheets(spreadsheet, historical=historical)
    logger.info("Done!")
    print(f"\n✅  Spreadsheet ready at:")
    print(f"    https://docs.google.com/spreadsheets/d/{spreadsheet.id}\n")


def setup_spreadsheet_by_id(gc: gspread.Client, spreadsheet_id: str, historical: bool = False) -> None:
    """Open a spreadsheet by ID and set up worksheets + headers.

    This is useful when you create the spreadsheet manually in your own
    Google Drive (avoiding the service-account quota) and then share it
    with the service account email so the script can configure it.
    """
    logger.info(f"Opening spreadsheet by ID: {spreadsheet_id} …")
    try:
        spreadsheet = gc.open_by_key(spreadsheet_id)
    except gspread.exceptions.SpreadsheetNotFound:
        logger.error(
            "Spreadsheet not found. Make sure the spreadsheet is shared with "
            "the service account email (shown above)."
        )
        return
    except gspread.exceptions.APIError as exc:
        if "403" in str(exc) or "PERMISSION_DENIED" in str(exc):
            logger.error(
                "Permission denied. Share the spreadsheet with the service "
                "account email (shown above) and grant Editor access."
            )
            return
        raise

    logger.info(f"Found spreadsheet: '{spreadsheet.title}'")
    logger.info("Setting up worksheets …")
    setup_worksheets(spreadsheet, historical=historical)

    # Clean up default 'Sheet1' if it still exists
    rate_limiter.wait_if_needed()
    try:
        sheet1 = spreadsheet.worksheet("Sheet1")
        spreadsheet.del_worksheet(sheet1)
        logger.info("  Removed leftover 'Sheet1'")
    except gspread.exceptions.WorksheetNotFound:
        pass

    logger.info("Done!")
    print(f"\n✅  Spreadsheet ready at:")
    print(f"    https://docs.google.com/spreadsheets/d/{spreadsheet.id}\n")

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="ApexBT — Google Sheets Setup Utility")
    parser.add_argument(
        "--creds",
        metavar="PATH",
        default=None,
        help="Path to Google service-account JSON file (skips AWS lookup)",
    )
    args = parser.parse_args()

    print("\n╔══════════════════════════════════════════╗")
    print("║   ApexBT — Google Sheets Setup Utility   ║")
    print("╚══════════════════════════════════════════╝\n")

    # Load credentials
    try:
        creds = get_sheets_credentials(cli_creds_path=args.creds)
    except Exception as exc:
        print(f"\n❌  Could not load Google Sheets credentials.\n")
        print(f"    {exc}\n")
        print("    Options:")
        print("      • python setup_sheets.py --creds /path/to/service_account.json")
        print("      • Place credentials.json in the current directory")
        print(f"      • Configure AWS profile '{AWS_PROFILE}' with valid credentials\n")
        sys.exit(1)

    gc = authorize_gspread(creds)
    service_email = creds.get("client_email", "unknown")
    logger.info("Authenticated with Google Sheets API")
    print(f"  Service account email: {service_email}\n")

    print("What would you like to do?\n")
    print(f"  1. Create new main sheet           ('{SPREADSHEET_NAME}')")
    print(f"  2. Create new historical sheet     ('{HISTORICAL_SPREADSHEET_NAME}')")
    print(f"  3. Re-initialize existing main sheet (by name)")
    print(f"  4. Re-initialize existing historical sheet (by name)")
    print(f"  5. Grant access to a sheet by ID")
    print(f"  6. Exit")
    print()
    print(f"  7. 🗑  Clean up service account Drive (fix quota errors)")
    print(f"  8. 📋 Set up a sheet by spreadsheet ID (recommended if quota exceeded)")
    print()

    choice = input("Enter your choice (1-8): ").strip()

    if choice == "1":
        sid = create_spreadsheet(gc, historical=False)
        grant_access(gc, sid, OWNER_EMAIL)

    elif choice == "2":
        sid = create_spreadsheet(gc, historical=True)
        grant_access(gc, sid, OWNER_EMAIL)

    elif choice == "3":
        setup_existing_spreadsheet(gc, SPREADSHEET_NAME, historical=False)

    elif choice == "4":
        setup_existing_spreadsheet(gc, HISTORICAL_SPREADSHEET_NAME, historical=True)

    elif choice == "5":
        sid = input("Spreadsheet ID: ").strip()
        if not sid:
            print("No ID provided.")
            sys.exit(1)
        email = input(f"Email to grant access [{OWNER_EMAIL}]: ").strip() or OWNER_EMAIL
        grant_access(gc, sid, email)

    elif choice == "6":
        print("Bye!")
        sys.exit(0)

    elif choice == "7":
        cleanup_service_account_drive(gc)
        print("You can now re-run this script and choose option 1 or 2.\n")

    elif choice == "8":
        print(f"\n📋 Set up worksheets on a spreadsheet you created manually.\n")
        print(f"   Step 1: Create a blank spreadsheet in YOUR Google Drive")
        print(f"   Step 2: Share it with the service account as Editor:")
        print(f"           {service_email}")
        print(f"   Step 3: Copy the spreadsheet ID from the URL:")
        print(f"           https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit")
        print()
        sid = input("Spreadsheet ID: ").strip()
        if not sid:
            print("No ID provided.")
            sys.exit(1)
        hist = input("Is this for historical data? [y/N]: ").strip().lower() in ("y", "yes")
        setup_spreadsheet_by_id(gc, sid, historical=hist)

    else:
        print("Invalid choice.")
        sys.exit(1)


if __name__ == "__main__":
    main()
