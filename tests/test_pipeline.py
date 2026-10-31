"""
Automated Test Suite for Email Automation System
Verifies data cleaning, email templating, SQLite persistence, and anti-spam safeguards.
"""
import unittest
import tempfile
import shutil
from pathlib import Path
import pandas as pd

from config import UserProfile
from data_processor.cleaner import (
    validate_email,
    clean_company_name,
    clean_recruiter_name,
    ContactDatasetCleaner
)
from templates.email_templates import TemplateEngine
from storage.tracker import OutreachTracker


class TestDataCleaning(unittest.TestCase):
    """Test data normalization, validation, and deduplication logic."""

    def test_email_validation(self):
        valid, email, err = validate_email("  Test.User@example.com  ")
        self.assertTrue(valid)
        self.assertEqual(email, "test.user@example.com")

        # Invalid formats
        self.assertFalse(validate_email("invalid-email")[0])
        self.assertFalse(validate_email("missing_at.domain.com")[0])
        self.assertFalse(validate_email("test@test.com")[0]) # Placeholder
        self.assertFalse(validate_email("")[0])
        self.assertFalse(validate_email(None)[0])

    def test_company_cleaning(self):
        self.assertEqual(clean_company_name("Google India Pvt Ltd"), "Google India")
        self.assertEqual(clean_company_name("Microsoft Corporation"), "Microsoft")
        self.assertEqual(clean_company_name("Stripe, Inc."), "Stripe")
        self.assertEqual(clean_company_name("Acme LLC"), "Acme")
        self.assertEqual(clean_company_name("Nexus Technologies (India)"), "Nexus Technologies")

    def test_recruiter_name_cleaning(self):
        name, first = clean_recruiter_name("JOHN DOE")
        self.assertEqual(name, "John Doe")
        self.assertEqual(first, "John")

        name, first = clean_recruiter_name("Ms. Priya Sharma")
        self.assertEqual(name, "Priya Sharma")
        self.assertEqual(first, "Priya")

        name, first = clean_recruiter_name("")
        self.assertEqual(name, "")
        self.assertEqual(first, "")

    def test_dataset_deduplication(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "test_contacts.xlsx"
            raw_data = [
                {"Name": "Alice Smith", "Company": "Acme Inc", "Email": "alice@acme.com", "Title": "Recruiter"},
                {"Name": "Alice S.", "Company": "Acme", "Email": " ALICE@acme.com ", "Title": "Senior Recruiter"}, # Duplicate
                {"Name": "Bad Contact", "Company": "NoMail", "Email": "invalid_email", "Title": "HR"}, # Invalid
                {"Name": "Bob Jones", "Company": "Beta Corp", "Email": "bob@beta.com", "Title": "HR Lead"}
            ]
            pd.DataFrame(raw_data).to_excel(tmp_path, index=False)

            cleaner = ContactDatasetCleaner(tmp_path)
            cleaned_df, quarantine_df, stats = cleaner.clean()

            self.assertEqual(len(cleaned_df), 2) # Alice and Bob
            self.assertEqual(len(quarantine_df), 2) # Duplicate Alice and invalid Bad Contact


class TestTemplateEngine(unittest.TestCase):
    """Test personalized template rendering and variable substitution."""

    def setUp(self):
        self.profile = UserProfile(
            full_name="Shreya Yadav",
            degree="B.Tech in Computer Science and Engineering",
            grad_year="2027",
            github_url="https://github.com/y-Shreya21",
            linkedin_url="https://www.linkedin.com/in/shreya-yadav-machinelearning/",
            portfolio_url="https://portfolio-shreya-kappa.vercel.app/",
            contact_phone="+91 6006608059",
            resume_path=Path("/non_existent_resume.pdf") # Test without attachment
        )
        self.engine = TemplateEngine(self.profile)

    def test_custom_template_rendering(self):
        contact = {
            "first_name": "Alex",
            "cleaned_name": "Alex Rivera",
            "cleaned_company": "Apex Technologies",
            "job_title": "Head of Talent Acquisition",
            "email": "alex.rivera@example.com"
        }
        res = self.engine.render(contact)
        body = res["text_body"]

        self.assertIn("Hi Alex,", body)
        self.assertIn("Apex Technologies", body)
        self.assertIn("B.Tech Computer Science Student", body)
        self.assertIn("Shreya Yadav", body)
        self.assertIn("+91 6006608059", body)
        self.assertIn("https://github.com/y-Shreya21", body)
        self.assertIn("https://portfolio-shreya-kappa.vercel.app/", body)
        # Ensure no unparsed Jinja brackets remain
        self.assertNotIn("{{", body)
        self.assertNotIn("}}", body)

    def test_missing_name_fallback(self):
        contact = {
            "first_name": "",
            "cleaned_name": "",
            "cleaned_company": "Nexus Systems",
            "email": "hr@example.com"
        }
        res = self.engine.render(contact)
        self.assertIn("Hi Nexus Systems Team,", res["text_body"])


class TestOutreachTracker(unittest.TestCase):
    """Test SQLite tracking, suppression filtering, and duplicate prevention."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.tmp_dir) / "test_tracker.db"
        self.supp_path = Path(self.tmp_dir) / "test_supp.json"
        self.tracker = OutreachTracker(self.db_path, self.supp_path)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_status_workflow(self):
        email = "lead@example.com"
        self.assertFalse(self.tracker.is_already_contacted(email))

        # Approve
        self.tracker.upsert_contact_status(email, name="John", company="Tech Corp", status="APPROVED", tier=1)
        self.assertFalse(self.tracker.is_already_contacted(email))

        # Draft
        self.tracker.upsert_contact_status(email, status="DRAFTED", draft_id="draft_123")
        self.assertTrue(self.tracker.is_already_contacted(email))

    def test_suppression(self):
        email = "optout@example.com"
        self.assertFalse(self.tracker.is_suppressed(email))

        self.tracker.add_to_suppression(email)
        self.assertTrue(self.tracker.is_suppressed(email))


if __name__ == "__main__":
    unittest.main()
