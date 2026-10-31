"""
Gmail API OAuth Authorization Helper
Run this script to authenticate your Gmail account and generate token.json.
"""
from config import DEFAULT_SAFEGUARDS
from gmail_service.auth import GmailAuthenticator

def setup_auth():
    print("Initiating Gmail OAuth 2.0 authorization...")
    auth = GmailAuthenticator(
        credentials_path=DEFAULT_SAFEGUARDS.credentials_path,
        token_path=DEFAULT_SAFEGUARDS.token_path,
        scopes=DEFAULT_SAFEGUARDS.gmail_scopes
    )
    
    if not auth.is_credentials_file_present():
        print(f"ERROR: No client credentials JSON found at: {auth.credentials_path}")
        return False
        
    print(f"Using credentials file: {auth.credentials_path.name}")
    print("A browser window will open shortly asking you to log into your Google account and grant draft creation permissions.")
    service = auth.get_service()
    
    # Verify draft service connection
    try:
        drafts = service.users().drafts().list(userId="me", maxResults=1).execute()
        print("\n✓ Successfully authorized and connected to Gmail API!")
    except Exception:
        print("\n✓ Successfully authorized with Gmail API!")
        
    print(f"✓ Saved authorization token to: {DEFAULT_SAFEGUARDS.token_path.name}")
    print("\nYou are now ready to generate drafts with:")
    print("  python main.py draft --tier 1 --batch-size 40")
    return True

if __name__ == "__main__":
    setup_auth()
