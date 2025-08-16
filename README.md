# Circe: Credit Card Statement Tracker

![Credit Card Tracker Banner](https://img.shields.io/badge/Credit%20Card%20Tracker-Python-blue?style=for-the-badge)

---

## 🤔 Why I Created Circe

I built Circe because I believe in keeping my financial data private and secure. Giving full access to my Gmail inbox to third-party apps like "Cred" felt risky and untrustworthy. Cred is packed with unnecessary features and I didn't want to share my sensitive information with an outside platform that I don't trust. So, as a real developer, I created my own credit card tracking utility—one that runs locally, keeps my data safe, and doesn't rely on any untrustworthy apps. Now, I can track my credit card bills with full control and peace of mind.

---

## 🚀 Features
- **Automatic Gmail Fetch**: Connects to your Gmail, finds statement emails, and downloads PDF attachments.
- **Secure PDF Parsing**: Uses your bank passwords to unlock and extract statement details.
- **Multi-bank Support**: Handles SBI, Axis, IndusInd, ICICI, Kotak, RBL, HDFC, BOB, and more.
- **Database Storage**: Saves parsed bills in a local SQLite database for easy tracking.
- **Rich Output**: Displays bills in a stylish, color-coded table using [Rich](https://github.com/Textualize/rich).

---

## 🛠️ Setup Instructions

### 1. Clone the Repository
```pwsh
# In PowerShell
git clone https://github.com/rahules24/Circe
cd Circe
```

### 2. Install Python & Dependencies
Make sure you have Python 3.8+ installed.
Install required packages:
```pwsh
pip install -r requirements.txt
```

### 3. Prepare Credentials
#### a. Gmail API Credentials
- Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
- Create OAuth 2.0 Client ID for Desktop
- Download `credentials.json` and place it in the `creds/` folder:
  - `Circe/creds/credentials.json`


#### b. Bank PDF Passwords (Supports Multiple Cards/Passwords)
- Add your bank passwords to `creds/passwords.json` in this format:
- You can add multiple users (e.g., `USER1`, `USER2`).
- For banks like SBI, where you might have multiple cards with different passwords, you can provide a list of passwords for that bank:
```json
{
  "USER1": {
    "sbi": ["password_for_card1", "password_for_card2"],
    "axis": "your_axis_password",
    ...
  },
  "USER2": {
    ...
  }
}
```
- The app will try each password in the list until it successfully unlocks the PDF.

#### c. Statement Sender Domains
- List statement sender domains in `cc_statements.txt` (one per line):
```
rblbank.com
axisbank.com
...
```

---

## 🔑 Authorizing Gmail Access
On first run, the app will:
- Prompt you to log in and authorize Gmail access in your browser.
- Save a token file (e.g., `creds/token_USER1.json`) for future runs.
- If you add more users, repeat the process for each.

---

## 📈 How It Works
1. **Authenticate Gmail**: Uses your credentials to connect to Gmail.
2. **Find Statement Emails**: Searches for recent emails from known bank domains with PDF attachments.
3. **Download & Parse PDFs**: Unlocks each PDF using your password, extracts statement data (due date, amount, card number, etc.) using robust pattern matching.
4. **Store in Database**: Saves parsed bills in `credit_statements.db`.
5. **Display Summary**: Shows a color-coded table of all bills for each user.

---


## 🖥️ Usage
Run the tracker from the command line:
```pwsh
python main.py
```

- You can add multiple users in the `USERS` list in `main.py` (e.g., `USERS = ['USER1', 'USER2']`).
- The app will process all users listed in `main.py`.
- If a user is missing a token, you’ll be prompted to authorize Gmail for that user.
- Parsed bills are shown in a stylish table.

---

## 📂 File Structure
- `main.py` — Main runner, orchestrates everything
- `parser.py` — PDF parsing logic
- `gmail_auth.py` — Gmail authentication & email fetching
- `requirements.txt` — Python dependencies
- `cc_statements.txt` — List of bank sender domains
- `creds/credentials.json` — Gmail API credentials
- `creds/passwords.json` — Bank PDF passwords
- `credit_statements.db` — SQLite database (auto-created)
- `creds/token_*.json` — Gmail OAuth tokens (auto-created)

---

## 🧑‍💻 Troubleshooting
- **Missing credentials.json**: Download from Google Cloud Console and place in `creds/`.
- **Missing passwords.json**: Add your bank passwords as shown above.
- **Gmail auth issues**: Delete the relevant `token_*.json` and re-run to re-authorize.
- **No bills found**: Check that your sender domains and passwords are correct.

---

> _"Track your credit card bills like a pro. Stay smart, stay secure!"_

---

## 🦸‍♂️ Contributing
Pull requests and suggestions welcome! Open an issue or PR to help improve Circe.
