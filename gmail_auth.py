import os
import base64
import logging
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

logger = logging.getLogger(__name__)

# Gmail API configuration
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def authenticate_gmail(user_id, creds_dir):
    """
    Handles authentication with Google Gmail API and returns a service object.
    
    Args:
        user_id (str): The user identifier (e.g., 'rahul', 'gulshan')
        creds_dir (str): Path to the credentials directory
        
    Returns:
        googleapiclient.discovery.Resource: Gmail service object or None if failed
    """
    creds = None
    token_path = os.path.join(creds_dir, f'token_{user_id}.json')
    credentials_path = os.path.join(creds_dir, 'credentials.json')

    # Load existing token if available
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    
    # If no valid credentials are available, get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Refresh expired token
            from google.auth.transport.requests import Request
            creds.refresh(Request())
        else:
            # Get new credentials
            if not os.path.exists(credentials_path):
                logger.error("'credentials.json' not found in '%s'.", creds_dir)
                return None
            
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
            
    return build('gmail', 'v1', credentials=creds)

def get_statement_emails(service, sender_list, days_to_search=45):
    """
    Searches Gmail for statement emails with PDF attachments from a list of senders.
    
    Args:
        service: Gmail service object from authenticate_gmail()
        sender_list (list): List of email domains to search for (e.g., ['rblbank.com', 'axisbank.com'])
        days_to_search (int): Number of days back to search for emails
        
    Returns:
        list: List of dictionaries containing PDF data, filename, and sender info
    """
    search_date = (datetime.now() - timedelta(days=days_to_search)).strftime('%Y/%m/%d')
    
    # Construct a query to find emails from any of the specified senders
    from_query = " OR ".join([f"from:{sender}" for sender in sender_list])
    query = f"({from_query}) has:attachment filename:pdf after:{search_date}"
    
    logger.debug("Searching Gmail with query: %s", query)
    
    try:
        result = service.users().messages().list(userId='me', q=query).execute()
        messages = result.get('messages', [])
        
        emails_with_attachments = []
        if not messages:
            return emails_with_attachments

        for msg in messages:
            try:
                msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
                payload = msg_data.get('payload', {})
                parts = payload.get('parts', [])
                
                # Get sender information
                sender = next((header['value'] for header in payload.get('headers', []) 
                             if header['name'].lower() == 'from'), "")

                # Look for PDF attachments
                for part in parts:
                    filename = part.get('filename', '')
                    if filename.lower().endswith('.pdf'):
                        attachment_id = part.get('body', {}).get('attachmentId')
                        if attachment_id:
                            # Download the attachment
                            attachment = service.users().messages().attachments().get(
                                userId='me', messageId=msg['id'], id=attachment_id
                            ).execute()
                            
                            # Decode the PDF data
                            pdf_data = base64.urlsafe_b64decode(attachment['data'].encode('UTF-8'))
                            
                            emails_with_attachments.append({
                                'pdf_data': pdf_data,
                                'filename': filename,
                                'sender': sender,
                                'message_id': msg['id']
                            })
                            
            except Exception as e:
                logger.debug("Failed to process message %s: %s", msg.get('id', 'unknown'), e)
                continue
                
        return emails_with_attachments
        
    except Exception as e:
        logger.error("Failed to search Gmail: %s", e)
        return []

def test_gmail_connection(user_id, creds_dir):
    """
    Test Gmail connection and authentication.
    
    Args:
        user_id (str): The user identifier
        creds_dir (str): Path to the credentials directory
        
    Returns:
        bool: True if connection successful, False otherwise
    """
    try:
        service = authenticate_gmail(user_id, creds_dir)
        if service:
            # Test the connection by getting user profile
            profile = service.users().getProfile(userId='me').execute()
            print(f"✓ Gmail connection successful for {user_id}")
            print(f"  Email: {profile.get('emailAddress', 'Unknown')}")
            print(f"  Total messages: {profile.get('messagesTotal', 'Unknown')}")
            return True
        else:
            print(f"✗ Gmail connection failed for {user_id}")
            return False
            
    except Exception as e:
        print(f"✗ Gmail connection test failed for {user_id}: {e}")
        return False

# For standalone testing
if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        user_id = sys.argv[1]
        creds_dir = os.path.join(os.path.dirname(__file__), 'creds')
        test_gmail_connection(user_id, creds_dir)
    else:
        print("Usage: python gmail_auth.py <user_id>")
        print("Example: python gmail_auth.py rahul")
