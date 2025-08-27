import os
import base64
import json
from datetime import datetime, timedelta
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import pikepdf
import getpass

# --- Configuration ---
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
YEARS_BACK = 2
MAX_ATTEMPTS = 3
ENABLED_BANKS = ['hdfc']  # Change to ['icici'], ['hdfc', 'icici'], etc.

BANK_PROFILES = {
    'hdfc': {
        'sender': 'Emailstatements.cards@hdfcbank.net',
        'subject': 'Diners Club International Credit Card Statement',
        'save_dir': 'hdfc_statements'
    },
    'icici': {
        'sender': 'noreply@icicibank.com',
        'subject': 'ICICI Bank Credit Card Statement',
        'save_dir': 'icici_statements'
    }
}

# --- Step 1: Authenticate Gmail ---
def authenticate_gmail():
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    creds = flow.run_local_server(port=0)
    return build('gmail', 'v1', credentials=creds)

# --- Step 2: Build Gmail Search Query ---
def build_query(sender, subject, years_back):
    cutoff = datetime.now() - timedelta(days=365 * years_back)
    return f'from:{sender} subject:"{subject}" filename:pdf after:{cutoff.strftime("%Y/%m/%d")}'

# --- Step 3: Search for Emails ---
def search_emails(service, query):
    results = service.users().messages().list(userId='me', q=query).execute()
    return [msg['id'] for msg in results.get('messages', [])]

# --- Step 4: Extract All Parts ---
def extract_all_parts(payload):
    parts, stack = [], [payload]
    while stack:
        current = stack.pop()
        stack.extend(current.get('parts', []))
        if 'body' in current:
            parts.append(current)
    return parts

# --- Step 5: Attachment Filter ---
def is_valid_attachment(part, bank):
    filename = part.get('filename', '').lower()
    mime = part.get('mimeType', '')
    if bank == 'hdfc':
        return filename.endswith('.pdf') or 'pdf' in mime or mime == 'application/octet-stream'
    if bank == 'icici':
        return filename.endswith('.pdf') or filename.endswith('.zip') or 'pdf' in mime
    return filename.endswith('.pdf')

# --- Step 6: Decryption Logic ---
def decrypt_pdf(temp_path, save_path, password, log_file):
    try:
        with pikepdf.open(temp_path, password=password) as pdf:
            pdf.save(save_path)
        print(f"✅ Decrypted: {save_path}")
        log_file.write(f"[{datetime.now()}] ✅ Decrypted: {save_path}\n")
        return True
    except pikepdf.PasswordError:
        print("❌ Incorrect password.")
        return False
    except Exception as e:
        print(f"⚠️ Error: {e}")
        log_file.write(f"[{datetime.now()}] ⚠️ Error decrypting {save_path}: {e}\n")
        return False

def decrypt_with_retry(temp_path, save_path, log_file):
    for attempt in range(1, MAX_ATTEMPTS + 1):
        pwd = getpass.getpass(f"🔐 Attempt {attempt}/{MAX_ATTEMPTS} — Enter PDF password: ")
        if decrypt_pdf(temp_path, save_path, pwd, log_file):
            return True
    failed_path = save_path.replace('.pdf', '_FAILED.pdf')
    os.rename(temp_path, failed_path)
    print(f"⏭️ Skipped after 3 failed attempts: {failed_path}")
    log_file.write(f"[{datetime.now()}] ❌ Failed: {failed_path}\n")
    return False

# --- Step 7: Download Attachments ---
def download_attachments(service, message_ids, save_dir, bank):
    os.makedirs(save_dir, exist_ok=True)
    log_file = open(os.path.join(save_dir, 'download_log.txt'), 'a')

    mode = input("🔐 Is the password same for all files? (yes/no): ").strip().lower()
    reuse_pwd = mode == 'yes'
    shared_pwd = None

    if reuse_pwd:
    # Find first valid attachment to test password
        test_path = None
        for msg_id in message_ids:
            msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
            parts = extract_all_parts(msg.get('payload', {}))
            for idx, part in enumerate(parts):
                if is_valid_attachment(part, bank):
                    body = part.get('body', {})
                    att_id = body.get('attachmentId')
                    if att_id:
                        att = service.users().messages().attachments().get(
                            userId='me', messageId=msg_id, id=att_id).execute()
                        data = base64.urlsafe_b64decode(att['data'].encode())
                        test_path = os.path.join(save_dir, f"temp_test_{msg_id}_{idx}.pdf")
                        with open(test_path, 'wb') as f:
                            f.write(data)
                        break
            if test_path:
                break

        if not test_path:
            print("⚠️ No valid attachment found to test password. Skipping password reuse.")
            reuse_pwd = False
        else:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                shared_pwd = getpass.getpass(f"🔑 Attempt {attempt}/{MAX_ATTEMPTS} — Enter PDF password: ")
                try:
                    with pikepdf.open(test_path, password=shared_pwd): pass
                    os.remove(test_path)
                    break
                except pikepdf.PasswordError:
                    print("❌ Incorrect password.")
                    shared_pwd = None
            if not shared_pwd:
                print("⛔ Failed to validate password. Exiting.")
                log_file.close()
                return

    for msg_id in message_ids:
        msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
        parts = extract_all_parts(msg.get('payload', {}))
        found = False

        for idx, part in enumerate(parts):
            if not is_valid_attachment(part, bank): continue
            filename = part.get('filename', f"{msg_id}_{idx}.pdf")
            body = part.get('body', {})
            att_id = body.get('attachmentId')
            data = None

            if att_id:
                att = service.users().messages().attachments().get(userId='me', messageId=msg_id, id=att_id).execute()
                data = base64.urlsafe_b64decode(att['data'].encode())
            elif 'data' in body:
                data = base64.urlsafe_b64decode(body['data'].encode())

            if data:
                temp_path = os.path.join(save_dir, f"temp_{msg_id}_{idx}.pdf")
                with open(temp_path, 'wb') as f: f.write(data)
                final_path = os.path.join(save_dir, filename)

                if reuse_pwd:
                    success = decrypt_pdf(temp_path, final_path, shared_pwd, log_file)
                    if not success:
                        failed_path = final_path.replace('.pdf', '_FAILED.pdf')
                        os.rename(temp_path, failed_path)
                        log_file.write(f"[{datetime.now()}] ❌ Failed: {failed_path}\n")
                    else:
                        os.remove(temp_path)
                        found = True
                else:
                    success = decrypt_with_retry(temp_path, final_path, log_file)
                    if success:
                        os.remove(temp_path)
                        found = True

        if not found:
            print(f"⚠️ No valid attachment in message {msg_id}")
            log_file.write(f"[{datetime.now()}] ⚠️ No valid attachment in message {msg_id}\n")

    log_file.close()
    print("🎉 All statements processed. Log saved.")

# --- Main ---
if __name__ == '__main__':
    print("🔐 Authenticating Gmail...")
    service = authenticate_gmail()

    for bank in ENABLED_BANKS:
        config = BANK_PROFILES.get(bank)
        if not config:
            print(f"⚠️ Bank profile for '{bank}' not found. Skipping.")
            continue

        print(f"\n🔍 Searching for {bank.upper()} statements...")
        query = build_query(config['sender'], config['subject'], YEARS_BACK)
        ids = search_emails(service, query)
        print(f"📨 Found {len(ids)} emails.")
        download_attachments(service, ids, config['save_dir'], bank)