# One-time setup script
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from sheets_config import SPREADSHEET_NAME, CREDENTIALS_FILE

def get_sheet_access():
    scope = ['https://spreadsheets.google.com/feeds',
             'https://www.googleapis.com/auth/drive']
    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        CREDENTIALS_FILE, scope)
    client = gspread.authorize(credentials)

    # Your spreadsheet ID
    spreadsheet = client.open_by_key('15IiBIGnmoLFCY8LWsU_gyjze6m5Na4qh-esgmCmIb8A')

    # Share with your email
    email = 'yhp2378@gmail.com'  # Replace with your email
    spreadsheet.share(email, perm_type='user', role='writer')

    print(f"Access granted! Open the spreadsheet at:")
    print(f"https://docs.google.com/spreadsheets/d/{spreadsheet.id}")

def setup_new_sheet():
    # Setup credentials
    scope = ['https://spreadsheets.google.com/feeds',
             'https://www.googleapis.com/auth/drive']
    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        CREDENTIALS_FILE, scope)

    # Authorize and create new spreadsheet
    gc = gspread.authorize(credentials)
    sh = gc.create(SPREADSHEET_NAME)

    # Get the first sheet
    worksheet = sh.get_worksheet(0)

    # Add headers
    headers = ['Tweet ID', 'Text', 'Created At', 'Timestamp']
    worksheet.append_row(headers)

    print(f"Created new spreadsheet: {sh.url}")
    print("Please share this spreadsheet with your Google account email")

if __name__ == "__main__":
    # setup_new_sheet()
    get_sheet_access()
