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
from data_processor.verifier import EmailDeliverabilityVerifier
from gmail_service.dispatcher import EmailDispatcher
from gmail_service.auth import MockGmailService


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


class TestDeliverabilityVerifier(unittest.TestCase):
    """Test email deliverability, syntax, burner detection, and MX verification."""

    def setUp(self):
        self.verifier = EmailDeliverabilityVerifier(dns_timeout=2.0, allow_offline_fallback=True)

    def test_syntax_checks(self):
        valid, _ = self.verifier.validate_syntax("recruiter@example.com")
        self.assertTrue(valid)

        invalid_cases = [
            "missing-at-domain.com",
            "@domain.com",
            "user@",
            "user@nodot",
            "",
            None
        ]
        for bad in invalid_cases:
            valid, _ = self.verifier.validate_syntax(bad)
            self.assertFalse(valid, f"Should fail for {bad}")

    def test_disposable_domain_detection(self):
        res = self.verifier.verify("applicant@mailinator.com")
        self.assertFalse(res.is_deliverable)
        self.assertEqual(res.status, "UNDELIVERABLE")
        self.assertIn("disposable/burner", res.reason)

        res2 = self.verifier.verify("lead@tempmail.com")
        self.assertFalse(res2.is_deliverable)
        self.assertEqual(res2.status, "UNDELIVERABLE")

    def test_nonexistent_domain(self):
        from unittest.mock import patch
        import dns.resolver

        with patch.object(self.verifier.resolver, "resolve", side_effect=dns.resolver.NXDOMAIN()):
            res = self.verifier.verify("recruiter@fake-company-does-not-exist.com")
            self.assertFalse(res.is_deliverable)
            self.assertEqual(res.status, "UNDELIVERABLE")
            self.assertIn("does not exist", res.reason)

    def test_domain_caching(self):
        domain = "mailinator.com"
        self.verifier.check_domain_mx(domain)
        self.assertIn(domain, self.verifier._domain_cache)

    def test_dispatcher_skips_undeliverable(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            db_path = Path(tmp_dir) / "test_tracker.db"
            supp_path = Path(tmp_dir) / "test_supp.json"
            tracker = OutreachTracker(db_path, supp_path)
            mock_service = MockGmailService()

            dispatcher = EmailDispatcher(
                gmail_service=mock_service,
                tracker=tracker,
                min_jitter=0,
                max_jitter=0,
                verifier=self.verifier
            )

            # Test undeliverable burner email
            success, msg, draft_id = dispatcher.create_draft(
                to_email="test@mailinator.com",
                subject="Test Subject",
                text_body="Hello",
                html_body="<p>Hello</p>"
            )

            self.assertFalse(success)
            self.assertIsNone(draft_id)
            self.assertIn("DELETED from queue", msg)
            self.assertIn("disposable/burner", msg)

            # Confirm contact is permanently purged from tracker per two-condition security rule
            with tracker._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT status FROM outreach_log WHERE email = ?", ("test@mailinator.com",))
                row = cursor.fetchone()
                self.assertIsNone(row)
        finally:
            shutil.rmtree(tmp_dir)

    def test_generic_and_system_inboxes(self):
        """Test Condition 1 rejection of generic, system, and billing mailboxes."""
        generic_emails = [
            "payable@awign.com",
            "billing@stripe.com",
            "invoices@acme.org",
            "noreply@company.com",
            "admin@domain.com",
            "support@helpdesk.io",
            "accounts@finance.com"
        ]
        for email in generic_emails:
            sec_res = self.verifier.security_check(email)
            self.assertFalse(sec_res.is_available, f"{email} should fail availability check")
            self.assertFalse(sec_res.can_draft, f"{email} should not be draftable")
            self.assertEqual(sec_res.action, "DELETE")
            self.assertIn("system/billing/bot", sec_res.reason)

    def test_legitimate_recruiter_availability(self):
        """Test Condition 1 accepts real recruiter and hiring manager addresses."""
        valid_recruiter_emails = [
            "priya.sharma@google.com",
            "john.doe@microsoft.com",
            "recruiter@amazon.com",
            "talent@startup.io"
        ]
        for email in valid_recruiter_emails:
            avail, _ = self.verifier.check_availability(email)
            self.assertTrue(avail, f"{email} should be available")

    def test_tracker_delete_contact(self):
        """Test OutreachTracker.delete_contact removes contact record permanently."""
        tmp_dir = tempfile.mkdtemp()
        try:
            db_path = Path(tmp_dir) / "test_tracker.db"
            supp_path = Path(tmp_dir) / "test_supp.json"
            tracker = OutreachTracker(db_path, supp_path)

            tracker.upsert_contact_status(
                email="test_delete@example.com",
                name="Delete Candidate",
                company="Delete Corp",
                status="APPROVED"
            )
            self.assertIsNotNone(tracker.get_contact("test_delete@example.com"))

            # Delete contact
            deleted = tracker.delete_contact("test_delete@example.com")
            self.assertTrue(deleted)
            self.assertIsNone(tracker.get_contact("test_delete@example.com"))

            # Non-existent contact returns False
            self.assertFalse(tracker.delete_contact("nonexistent@example.com"))
        finally:
            shutil.rmtree(tmp_dir)

    def test_dispatcher_delete_draft(self):
        """Test dispatcher.delete_draft properly interfaces with Gmail service."""
        mock_service = MockGmailService()
        tracker = OutreachTracker(Path(":memory:"), Path("/tmp/supp.json"))
        dispatcher = EmailDispatcher(mock_service, tracker)

        # Mock draft IDs return True
        self.assertTrue(dispatcher.delete_draft("mock_draft_12345"))
        self.assertTrue(dispatcher.delete_draft(""))

    def test_dry_run_isolation(self):
        """Test that dry-run mode never mutates SQLite status, counters, or deletes records."""
        tmp_dir = tempfile.mkdtemp()
        try:
            db_path = Path(tmp_dir) / "test_tracker.db"
            supp_path = Path(tmp_dir) / "test_supp.json"
            tracker = OutreachTracker(db_path, supp_path)
            mock_service = MockGmailService()

            # Seed an approved contact
            tracker.upsert_contact_status(
                email="candidate@example.com",
                name="Candidate",
                company="Test Corp",
                status="APPROVED"
            )

            dispatcher = EmailDispatcher(
                mock_service,
                tracker,
                min_jitter=0,
                max_jitter=0,
                verifier=self.verifier,
                is_dry_run=True
            )

            # 1. Test create_draft in dry-run
            success, msg, draft_id = dispatcher.create_draft(
                to_email="candidate@example.com",
                subject="Test Subject",
                text_body="Test Body",
                html_body="<p>Test Body</p>"
            )
            self.assertTrue(success)
            self.assertEqual(tracker.get_daily_count("drafts_count"), 0)
            contact = tracker.get_contact("candidate@example.com")
            self.assertEqual(contact["status"], "APPROVED")

            # 2. Test send_email in dry-run
            success, msg, msg_id = dispatcher.send_email(
                to_email="candidate@example.com",
                subject="Test Subject",
                text_body="Test Body",
                html_body="<p>Test Body</p>"
            )
            self.assertTrue(success)
            self.assertEqual(tracker.get_daily_count("sent_count"), 0)
            contact = tracker.get_contact("candidate@example.com")
            self.assertEqual(contact["status"], "APPROVED")

            # 3. Test that undeliverable contact is NOT deleted from database during dry-run
            tracker.upsert_contact_status(
                email="burner@mailinator.com",
                name="Burner",
                company="Burner Inc",
                status="APPROVED"
            )
            success, msg, _ = dispatcher.create_draft(
                to_email="burner@mailinator.com",
                subject="Test",
                text_body="Test",
                html_body="<p>Test</p>"
            )
            self.assertFalse(success)
            self.assertIn("WOULD DELETE", msg)
            # Contact must still exist in SQLite because it was a dry-run
            self.assertIsNotNone(tracker.get_contact("burner@mailinator.com"))
        finally:
            shutil.rmtree(tmp_dir)

    def test_dry_run_allows_send_at_daily_limit(self):
        """Test that daily sending limit check only blocks live sends, not dry-run simulations."""
        tmp_dir = tempfile.mkdtemp()
        try:
            db_path = Path(tmp_dir) / "test_tracker.db"
            supp_path = Path(tmp_dir) / "test_supp.json"
            tracker = OutreachTracker(db_path, supp_path)
            mock_service = MockGmailService()

            # Simulate hitting the 50 emails daily limit
            with tracker._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO daily_quota_tracker (send_date, sent_count) VALUES (date('now'), 50)"
                )
                conn.commit()

            # Live dispatcher should abort
            live_disp = EmailDispatcher(mock_service, tracker, min_jitter=0, max_jitter=0, is_dry_run=False)
            success, msg, _ = live_disp.send_email(
                to_email="test@example.com",
                subject="Sub",
                text_body="Body",
                html_body="<p>Body</p>"
            )
            self.assertFalse(success)
            self.assertIn("Daily limit reached", msg)

            # Dry-run dispatcher should simulate successfully without blocking
            dry_disp = EmailDispatcher(mock_service, tracker, min_jitter=0, max_jitter=0, is_dry_run=True)
            success, msg, _ = dry_disp.send_email(
                to_email="test@example.com",
                subject="Sub",
                text_body="Body",
                html_body="<p>Body</p>"
            )
            self.assertTrue(success)
            self.assertIn("Email sent successfully", msg)
        finally:
            shutil.rmtree(tmp_dir)

    def test_explicit_dry_run_false_with_mock(self):
        """Test that explicitly passing is_dry_run=False with mock service mutates tracker as expected."""
        tmp_dir = tempfile.mkdtemp()
        try:
            db_path = Path(tmp_dir) / "test_tracker.db"
            supp_path = Path(tmp_dir) / "test_supp.json"
            tracker = OutreachTracker(db_path, supp_path)
            mock_service = MockGmailService()

            dispatcher = EmailDispatcher(mock_service, tracker, min_jitter=0, max_jitter=0, is_dry_run=False)
            self.assertFalse(dispatcher.is_dry_run)

            success, msg, draft_id = dispatcher.create_draft(
                to_email="new_lead@example.com",
                subject="Draft Test",
                text_body="Body",
                html_body="<p>Body</p>"
            )
            self.assertTrue(success)
            self.assertEqual(tracker.get_daily_count("drafts_count"), 1)
            contact = tracker.get_contact("new_lead@example.com")
            self.assertIsNotNone(contact)
            self.assertEqual(contact["status"], "DRAFTED")
        finally:
            shutil.rmtree(tmp_dir)


if __name__ == "__main__":
    unittest.main()

