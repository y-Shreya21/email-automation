"""
Synthetic HR / Recruiter Dataset Generator for Testing & Verification
Creates a realistic 2,000-contact dataset with duplicates, formatting variations, and edge cases.
"""
import random
from pathlib import Path
import pandas as pd

FIRST_NAMES = [
    "Aarav", "Aditi", "Rohan", "Priya", "Ananya", "Rahul", "Neha", "Vikram", 
    "Sneha", "Karan", "Pooja", "Arjun", "Kavya", "Amit", "Divya", "Siddharth",
    "John", "Sarah", "Michael", "Emily", "David", "Jessica", "James", "Rachel"
]

LAST_NAMES = [
    "Sharma", "Verma", "Patel", "Gupta", "Mehta", "Reddy", "Nair", "Singh",
    "Chopra", "Iyer", "Rao", "Joshi", "Smith", "Johnson", "Williams", "Brown", "Taylor"
]

COMPANIES = [
    ("Google India Pvt Ltd", "google.com"),
    ("Microsoft Corporation", "microsoft.com"),
    ("Amazon Development Centre", "amazon.com"),
    ("Adobe Systems Inc.", "adobe.com"),
    ("Goldman Sachs Services LLC", "gs.com"),
    ("Uber Technologies Inc.", "uber.com"),
    ("Zomato Limited", "zomato.com"),
    ("Swiggy Pvt. Ltd.", "swiggy.in"),
    ("Flipkart Internet Pvt Ltd", "flipkart.com"),
    ("PhonePe Private Limited", "phonepe.com"),
    ("Salesforce India LLC", "salesforce.com"),
    ("Cisco Systems India", "cisco.com"),
    ("NVIDIA Graphics Pvt Ltd", "nvidia.com"),
    ("Atlassian Corporation", "atlassian.com"),
    ("Intuit India Software Solutions", "intuit.com"),
    ("Oracle India Pvt. Ltd.", "oracle.com"),
    ("Morgan Stanley Advantage Services", "morganstanley.com"),
    ("JPMorgan Chase & Co.", "jpmorgan.com")
]

TITLES = [
    "University Recruiter", "Campus Talent Acquisition Lead", "Technical Recruiter",
    "Senior Recruiter - AI/ML", "Lead Tech Recruiter (SWE)", "HR Manager",
    "Early Careers Specialist", "Talent Acquisition Partner - Engineering",
    "Recruitment Consultant", "People Operations Lead"
]

LOCATIONS = [
    "Bengaluru, Karnataka", "Hyderabad, Telangana", "Gurugram, Haryana",
    "Noida, Uttar Pradesh", "Pune, Maharashtra", "Mumbai, Maharashtra",
    "San Francisco, CA", "Remote - India"
]


def generate_sample_dataset(num_records: int = 2000, output_path: Path = Path("sample_recruiter_contacts.xlsx")) -> Path:
    """Generate realistic spreadsheet with intentional duplicates and dirty edge cases."""
    records = []
    
    print(f"Generating {num_records} synthetic recruiter contacts...")

    for i in range(num_records):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        company_name, domain = random.choice(COMPANIES)
        title = random.choice(TITLES)
        location = random.choice(LOCATIONS)

        # Name variations (e.g. ALL CAPS, title with salutation)
        name_style = random.random()
        if name_style < 0.15:
            full_name = f"{first} {last}".upper()
        elif name_style < 0.25:
            full_name = f"Ms. {first} {last}" if random.random() > 0.5 else f"Mr. {first} {last}"
        elif name_style < 0.30:
            full_name = "" # Missing name test case
        else:
            full_name = f"{first} {last}"

        # Email variations
        email_style = random.random()
        if email_style < 0.05:
            # Missing email
            email = ""
        elif email_style < 0.08:
            # Invalid email syntax
            email = f"{first.lower()}.{last.lower()}@{domain}_invalid"
        elif email_style < 0.10:
            # Placeholder email
            email = "recruiter@company.com"
        else:
            email = f"{first.lower()}.{last.lower()}@{domain}"

        records.append({
            "Recruiter Name": full_name,
            "Company Name": company_name,
            "Email Address": email,
            "Job Title": title,
            "Location": location
        })

    # Intentionally inject 150 duplicate email records across the dataset
    for _ in range(150):
        source = random.choice(records)
        dup = source.copy()
        # vary capitalization or spacing in duplicate
        dup["Email Address"] = f"  {dup['Email Address'].upper()}  "
        records.append(dup)

    df = pd.DataFrame(records)
    # Shuffle
    df = df.sample(frac=1.0, random_state=42).reset_index(drop=True)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(output_path, index=False)
    print(f"✓ Created sample dataset with {len(df)} rows at: {output_path}")
    return output_path


if __name__ == "__main__":
    generate_sample_dataset()
