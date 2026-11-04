"""
System Configuration for Automated HR Email Outreach System
"""
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional

# Base directory
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"

# Ensure runtime directories exist
DATA_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

def get_default_resume_path() -> Path:
    """Auto-detect resume PDF in workspace root."""
    default = BASE_DIR / "resume.pdf"
    if default.exists():
        return default
    pdfs = [f for f in BASE_DIR.glob("*.pdf") if not f.name.startswith(".")]
    if pdfs:
        return pdfs[0]
    return default


@dataclass
class UserProfile:
    full_name: str = "Shreya Yadav"
    degree: str = "B.Tech in Computer Science and Engineering"
    college: str = "Computer Science Department"
    grad_year: str = "2027"
    primary_roles: str = "Software Engineering, AI/ML, and Full-Stack Development"
    
    # Template specific fields
    current_designation: str = "B.Tech Computer Science Student"
    experience_phrase: str = "hands-on project experience in AI/ML and Software Engineering"
    target_role: str = "Software Engineering / AI-ML Intern"
    
    achievement_1: str = "Strong foundational expertise in Data Structures, Algorithms, and scalable software development"
    achievement_2: str = "Hands-on experience building ML/Deep Learning models and end-to-end data pipelines in Python"
    achievement_3: str = "Active open-source projects showcased on GitHub and personal web portfolio"
    
    # Portfolio & Social Links
    github_url: str = "https://github.com/y-Shreya21"
    linkedin_url: str = "https://www.linkedin.com/in/shreya-yadav-machinelearning/"
    portfolio_url: Optional[str] = "https://portfolio-shreya-kappa.vercel.app/"
    
    # Contact info
    contact_phone: Optional[str] = "+91 6006608059"
    email_address: Optional[str] = "shreyayadav2027@gmail.com"
    
    # Path to resume PDF (relative or absolute)
    resume_path: Path = field(default_factory=get_default_resume_path)

@dataclass
class AntiSpamSettings:
    # Safe limits to preserve Gmail domain reputation
    max_emails_per_day: int = 50
    min_jitter_seconds: int = 20
    max_jitter_seconds: int = 45
    
    # Gmail API scopes: minimal compose scope needed for drafts & sending
    gmail_scopes: List[str] = field(default_factory=lambda: [
        "https://www.googleapis.com/auth/gmail.compose"
    ])
    
    # Credentials paths
    credentials_path: Path = BASE_DIR / "credentials.json"
    token_path: Path = BASE_DIR / "token.json"

@dataclass
class StorageSettings:
    db_path: Path = DATA_DIR / "outreach_history.db"
    suppression_list_path: Path = DATA_DIR / "suppression_list.json"
    cleaned_contacts_path: Path = DATA_DIR / "cleaned_contacts.xlsx"
    quarantined_records_path: Path = DATA_DIR / "quarantined_records.xlsx"
    audit_log_path: Path = DATA_DIR / "outreach.log"
    preview_dashboard_path: Path = REPORTS_DIR / "preview_dashboard.html"

# Global default instances
DEFAULT_PROFILE = UserProfile()
DEFAULT_SAFEGUARDS = AntiSpamSettings()
DEFAULT_STORAGE = StorageSettings()
