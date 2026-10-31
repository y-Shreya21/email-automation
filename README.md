# Automated HR Email Outreach System

An automated, personalized, anti-spam-compliant outreach pipeline built with Python, Pandas, Jinja2, Rich, and the official Gmail API. Tailored for B.Tech Computer Science students seeking internships and entry-level opportunities in Software Engineering and AI/ML.

---

## 📁 Project Structure

```text
email_automation/
├── config.py                   # User profile, rate limits, file paths
├── main.py                     # CLI orchestrator
├── requirements.txt            # Python dependencies
├── generate_sample_data.py     # 2,000-contact sample spreadsheet generator
│
├── data_processor/
│   ├── __init__.py
│   └── cleaner.py              # Column detection, RFC validation, deduplication
│
├── templates/
│   ├── __init__.py
│   └── email_templates.py      # AI/ML, SWE, General templates & spam auditor
│
├── storage/
│   ├── __init__.py
│   └── tracker.py              # SQLite audit trail, duplicate prevention, opt-out suppression
│
├── gmail_service/
│   ├── __init__.py
│   ├── auth.py                 # OAuth 2.0 flow & token management
│   └── dispatcher.py           # MIME multipart builder, draft creation, jitter, sending
│
├── ui/
│   ├── __init__.py
│   └── preview_system.py       # Rich terminal preview & HTML visual dashboard
│
├── data/
│   ├── cleaned_contacts.xlsx   # Output: sanitized & deduplicated contacts
│   ├── quarantined_records.xlsx# Output: invalid emails & duplicate logs
│   ├── outreach_history.db     # SQLite persistence database
│   └── suppression_list.json   # Opt-out & bounced email blacklist
│
└── reports/
    └── preview_dashboard.html  # Standalone visual preview dashboard
```

---

## 🚀 Quick Start Guide

### 1. Activate Environment
```bash
cd /Users/shreyayadav/Downloads/email_automation
source venv/bin/activate
```

### 2. Configure Your Profile (`config.py`)
Open `config.py` and customize:
- `full_name`: Your name (default: `"Shreya Yadav"`)
- `degree`: Your degree and major
- `grad_year`: Expected graduation year
- `github_url`: Your GitHub profile link
- `linkedin_url`: Your LinkedIn profile link
- `portfolio_url`: (Optional) Your personal portfolio

Place your resume named **`resume.pdf`** in this project folder (`/Users/shreyayadav/Downloads/email_automation/resume.pdf`). The system will automatically attach it to drafts and emails!

---

## 🛠️ Step-by-Step Workflow

### Step 1: Place Your Excel File & Clean It
Copy your recruiter spreadsheet (e.g., `contacts.xlsx` or `recruiter_list.xlsx`) into this project directory.

Run:
```bash
python main.py clean --file contacts.xlsx
```
*(If `--file` is omitted, the system will automatically detect the spreadsheet in the folder)*.

**What happens:**
- Columns (`Name`, `Company`, `Email`, `Job Title`, `Location`) are automatically mapped.
- Duplicate email addresses are identified and removed.
- Invalid syntax and missing emails are quarantined in `data/quarantined_records.xlsx` with explicit reasons.
- Company names are cleaned of legal suffixes (`LLC`, `Pvt Ltd`, `Inc.`) for natural email phrasing.
- Cleaned contacts are exported to `data/cleaned_contacts.xlsx`.

---

### Step 2: Preview & Approve Emails

#### Option A: Interactive Terminal Preview
```bash
python main.py preview
```
- Inspect each personalized email card one by one.
- Press `[A]` to Approve, `[R]` to Reject/Skip, `[B]` to Batch Approve All, `[Q]` to Save & Quit.

#### Option B: Visual Web Dashboard (Recommended)
```bash
python main.py dashboard --limit 100
```
Open the generated HTML dashboard in your browser:
`file:///Users/shreyayadav/Downloads/email_automation/reports/preview_dashboard.html`
- Search and filter by contact, company, or status.
- Click **"Inspect Full Email"** to preview the exact rendered HTML layout and signature.

#### Option C: Fast Batch Approve
If you are satisfied with the cleaned list:
```bash
python main.py approve-all
```

---

### Step 3: Connect Gmail & Create Drafts (Recommended)

To create drafts inside your real Gmail account:
1. Obtain `credentials.json` from [Google Cloud Console](https://console.cloud.google.com/):
   - Enable **Gmail API** (APIs & Services > Library > Gmail API).
   - Create Credentials > OAuth Client ID > Application Type: **Desktop App**.
   - Download the client secrets JSON and save it as **`credentials.json`** in this folder.
2. Run Draft Creation:
```bash
python main.py draft --batch-size 40
```
*(The first time you run this, a browser tab will open asking you to grant permission. Once authorized, `token.json` is saved locally).*

#### Dry-Run Mode (Test without Gmail API credentials)
You can test the entire draft generation pipeline right now without credentials:
```bash
python main.py draft --batch-size 10 --dry-run
```

---

### Step 4: Direct Sending (With Safeguards)

To directly send individual emails to approved recipients:
```bash
python main.py send --batch-size 20 --confirm-send
```

> [!CAUTION]
> **Safety Guard**: Direct sending requires the explicit `--confirm-send` flag. Emails are sent **1-to-1 individually** with randomized anti-spam jitter (20–45s) between sends. No recipients are ever exposed to each other.

---

### Step 5: Check Status & Metrics
```bash
python main.py status
```
Displays:
- Total contacts tracked in database
- Number of approved, drafted, sent, and rejected contacts
- Today's draft and send counters against daily quota limits
- Suppressed/opted-out contacts

---

## 🛡️ Anti-Spam & Deliverability Best Practices

1. **Daily Volume**: Keep your daily sends between **30–50 emails/day** for a standard personal `@gmail.com` account. Never exceed 100/day.
2. **Draft First**: Creating drafts in Gmail gives you the opportunity to spot-check emails in Gmail before clicking send.
3. **Opt-Out Compliance**: All email templates include an unobtrusive opt-out footer. If any recruiter replies to unsubscribe, add their email to `data/suppression_list.json` or use `tracker.add_to_suppression("email@company.com")`.
4. **Resend Prevention**: The SQLite database prevents contacting the same email address twice, even across multiple campaign runs.
