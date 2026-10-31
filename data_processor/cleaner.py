"""
Data Cleaning, Normalization, and Column Mapping Engine
"""
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import pandas as pd

# Standard regex for email validation
EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
)

# Common legal and corporate suffixes to strip for natural conversational phrasing
LEGAL_SUFFIXES_REGEX = re.compile(
    r"\b(pvt\.?\s*ltd\.?|private\s+limited|llc|inc\.?|incorporated|corp\.?|corporation|ltd\.?|limited|co\.?|gmbh|llp|holdings)\b",
    re.IGNORECASE
)

# Known dummy/placeholder emails to discard
PLACEHOLDER_EMAILS = {
    "test@test.com", "example@example.com", "info@example.com", 
    "hr@company.com", "recruiter@company.com", "none@none.com",
    "na@na.com", "nil@nil.com", "admin@domain.com"
}

COLUMN_SYNONYMS = {
    "name": [
        "hr name", "recruiter name", "recruiter", "contact name", "name", 
        "contact person", "full name", "first name", "lead name", "person"
    ],
    "company": [
        "company name", "company", "organization", "organisation", "employer", 
        "firm", "business name", "client", "workplace"
    ],
    "email": [
        "email", "email address", "hr email", "contact email", "work email", 
        "recruiter email", "e-mail", "mail", "official email"
    ],
    "role": [
        "job title", "title", "designation", "role", "position", 
        "recruiter title", "current role", "function"
    ],
    "location": [
        "location", "city", "country", "office", "headquarters", 
        "region", "state", "work location"
    ]
}


def clean_company_name(raw_name: Any) -> str:
    """Clean company name for conversational use (removes LLC, Inc, etc.)."""
    if not raw_name or pd.isna(raw_name):
        return ""
    
    name = str(raw_name).strip()
    # Remove text in parentheses like (India) or (US)
    name = re.sub(r"\s*\([^)]*\)", "", name)
    # Strip legal suffixes
    cleaned = LEGAL_SUFFIXES_REGEX.sub("", name).strip()
    # Strip trailing punctuation
    cleaned = re.sub(r"[\s,.-]+$", "", cleaned).strip()
    return cleaned if cleaned else name


def clean_recruiter_name(raw_name: Any) -> Tuple[str, str]:
    """
    Clean recruiter full name and extract a proper first name.
    Returns: (cleaned_full_name, first_name)
    """
    if not raw_name or pd.isna(raw_name):
        return ("", "")
    
    name = str(raw_name).strip()
    # Remove salutations
    name = re.sub(r"^(mr\.?|ms\.?|mrs\.?|dr\.?)\s+", "", name, flags=re.IGNORECASE).strip()
    
    # Title-case correctly while handling all-caps
    name = " ".join(part.capitalize() for part in name.split())
    parts = name.split()
    first_name = parts[0] if parts else ""
    
    return (name, first_name)


def validate_email(raw_email: Any) -> Tuple[bool, str, str]:
    """
    Validate and normalize email.
    Returns: (is_valid, normalized_email, error_reason)
    """
    if not raw_email or pd.isna(raw_email):
        return (False, "", "Missing email address")
    
    email = str(raw_email).strip().lower()
    # Strip prefix like mailto:
    if email.startswith("mailto:"):
        email = email[7:].strip()
    
    # Strip whitespace, brackets, quotes
    email = email.strip("<>\"' \t\r\n")
    
    if not email:
        return (False, "", "Empty email address")
    
    if email in PLACEHOLDER_EMAILS:
        return (False, email, "Placeholder/Dummy email detected")
    
    if not EMAIL_REGEX.match(email):
        return (False, email, "Invalid email syntax (RFC 5322)")
    
    # Domain syntax checks
    domain = email.split("@")[1]
    if "." not in domain or domain.endswith(".") or domain.startswith("."):
        return (False, email, "Invalid domain structure")
    
    return (True, email, "")


class ContactDatasetCleaner:
    """Handles Excel ingestion, column detection, deduplication, and export."""

    def __init__(self, file_path: Path):
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"Source file not found at: {self.file_path}")
        
        self.raw_df = self._load_file()
        self.column_mapping: Dict[str, str] = {}
        self.cleaned_df = pd.DataFrame()
        self.quarantine_df = pd.DataFrame()
        self.stats: Dict[str, Any] = {}

    def _load_file(self) -> pd.DataFrame:
        """Load file based on extension (.xlsx, .xls, .csv)."""
        suffix = self.file_path.suffix.lower()
        if suffix in [".xlsx", ".xls"]:
            return pd.read_excel(self.file_path)
        elif suffix == ".csv":
            return pd.read_csv(self.file_path)
        else:
            raise ValueError(f"Unsupported file format: {suffix}. Expected .xlsx, .xls, or .csv")

    def detect_columns(self) -> Dict[str, str]:
        """Detect and map standard fields based on header synonyms."""
        detected = {}
        headers = [str(col).strip() for col in self.raw_df.columns]
        headers_lower = {col.lower(): col for col in headers}

        for field, synonyms in COLUMN_SYNONYMS.items():
            for syn in synonyms:
                if syn in headers_lower:
                    detected[field] = headers_lower[syn]
                    break
        
        # If email not detected yet, scan first few non-null values for '@' symbol
        if "email" not in detected:
            for col in self.raw_df.columns:
                sample_values = self.raw_df[col].dropna().astype(str).head(10)
                if any("@" in val and "." in val for val in sample_values):
                    detected["email"] = col
                    break
        
        self.column_mapping = detected
        return detected

    def clean(self) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
        """
        Execute full cleaning pipeline:
        1. Validate emails
        2. Clean names and company names
        3. Deduplicate
        4. Quarantine invalid and duplicate records
        """
        if not self.column_mapping:
            self.detect_columns()
        
        email_col = self.column_mapping.get("email")
        if not email_col:
            raise ValueError(
                f"Could not identify an Email column in spreadsheet. Available columns: {list(self.raw_df.columns)}"
            )

        name_col = self.column_mapping.get("name")
        company_col = self.column_mapping.get("company")
        role_col = self.column_mapping.get("role")
        location_col = self.column_mapping.get("location")

        valid_rows = []
        quarantine_rows = []
        seen_emails = set()

        total_input_rows = len(self.raw_df)

        for idx, row in self.raw_df.iterrows():
            raw_email = row.get(email_col, "")
            is_valid, normalized_email, error_reason = validate_email(raw_email)

            # Preserve all original row attributes
            record = row.to_dict()
            record["_original_index"] = idx + 2 # 1-indexed Excel row (+1 for header)

            if not is_valid:
                record["rejection_reason"] = error_reason
                quarantine_rows.append(record)
                continue

            # Check duplicates
            if normalized_email in seen_emails:
                record["rejection_reason"] = f"Duplicate email address ({normalized_email})"
                quarantine_rows.append(record)
                continue

            # Process names
            raw_name = row.get(name_col, "") if name_col else ""
            clean_name, first_name = clean_recruiter_name(raw_name)

            # Process company
            raw_comp = row.get(company_col, "") if company_col else ""
            clean_comp = clean_company_name(raw_comp)

            # Process role & location
            clean_role = str(row.get(role_col, "")).strip() if role_col and not pd.isna(row.get(role_col)) else ""
            clean_loc = str(row.get(location_col, "")).strip() if location_col and not pd.isna(row.get(location_col)) else ""

            # Detect strategic tier
            raw_cat = str(row.get("Category", "")).lower()
            if "mnc" in raw_cat or "funded" in raw_cat:
                tier = 1
            elif "it services" in raw_cat or "software" in raw_cat:
                tier = 2
            elif "staffing" in raw_cat or "agencies" in raw_cat:
                tier = 3
            else:
                tier = 1

            record["email"] = normalized_email
            record["cleaned_name"] = clean_name
            record["first_name"] = first_name
            record["cleaned_company"] = clean_comp
            record["job_title"] = clean_role
            record["location"] = clean_loc
            record["tier"] = tier

            seen_emails.add(normalized_email)
            valid_rows.append(record)

        self.cleaned_df = pd.DataFrame(valid_rows)
        self.quarantine_df = pd.DataFrame(quarantine_rows)

        self.stats = {
            "total_input_records": total_input_rows,
            "valid_contacts": len(self.cleaned_df),
            "quarantined_records": len(self.quarantine_df),
            "unique_emails": len(seen_emails),
            "column_mapping": self.column_mapping
        }

        return self.cleaned_df, self.quarantine_df, self.stats

    def export(self, cleaned_path: Path, quarantine_path: Path) -> Tuple[Path, Path]:
        """Export cleaned contacts and quarantined records to Excel files."""
        cleaned_path = Path(cleaned_path)
        quarantine_path = Path(quarantine_path)
        
        cleaned_path.parent.mkdir(parents=True, exist_ok=True)
        quarantine_path.parent.mkdir(parents=True, exist_ok=True)

        # Write cleaned contacts
        if not self.cleaned_df.empty:
            self.cleaned_df.to_excel(cleaned_path, index=False)
        else:
            pd.DataFrame().to_excel(cleaned_path, index=False)

        # Write quarantine records
        if not self.quarantine_df.empty:
            self.quarantine_df.to_excel(quarantine_path, index=False)
        else:
            pd.DataFrame().to_excel(quarantine_path, index=False)

        return cleaned_path, quarantine_path
