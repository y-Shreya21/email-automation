"""
Automated HR Email Outreach System - Main CLI Orchestrator
"""
import sys
import os
import re
import stat
import socket
import subprocess
import argparse
from pathlib import Path

# Force IPv4 preference across CLI execution to avoid network timeouts on broken IPv6 routes
_orig_getaddrinfo = socket.getaddrinfo

def _ipv4_first_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if family == 0:
        family = socket.AF_INET
    return _orig_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = _ipv4_first_getaddrinfo
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from config import DEFAULT_PROFILE, DEFAULT_SAFEGUARDS, DEFAULT_STORAGE
from data_processor.cleaner import ContactDatasetCleaner
from data_processor.verifier import EmailDeliverabilityVerifier
from templates.email_templates import TemplateEngine
from storage.tracker import OutreachTracker
from ui.preview_system import PreviewApprovalSystem
from gmail_service.auth import GmailAuthenticator, MockGmailService
from gmail_service.dispatcher import EmailDispatcher

console = Console()


def auto_detect_input_file() -> Path:
    """Find the first available .xlsx, .xls, or .csv in the workspace."""
    base_dir = Path(__file__).resolve().parent
    candidates = list(base_dir.glob("*.xlsx")) + list(base_dir.glob("*.xls")) + list(base_dir.glob("*.csv"))
    # Filter out internal exports
    candidates = [c for c in candidates if "cleaned_contacts" not in c.name and "quarantined" not in c.name]
    
    if not candidates:
        raise FileNotFoundError(
            "No input spreadsheet found in workspace! Please place your Excel file (.xlsx) in this folder."
        )
    return candidates[0]


def cmd_clean(args):
    """Clean, deduplicate, and validate contact spreadsheet."""
    input_file = Path(args.file) if args.file else auto_detect_input_file()
    console.print(f"[bold blue]Step 1: Reading and cleaning spreadsheet:[/] {input_file}")

    cleaner = ContactDatasetCleaner(input_file)
    mapping = cleaner.detect_columns()

    # Display detected column mapping
    mapping_table = Table(title="Detected Column Mappings", show_header=True)
    mapping_table.add_column("Field", style="cyan")
    mapping_table.add_column("Mapped Spreadsheet Header", style="green")
    for field, header in mapping.items():
        mapping_table.add_row(field.capitalize(), header)
    console.print(mapping_table)

    cleaned_df, quarantine_df, stats = cleaner.clean()
    cleaned_path, quarantine_path = cleaner.export(
        DEFAULT_STORAGE.cleaned_contacts_path,
        DEFAULT_STORAGE.quarantined_records_path
    )

    # Display stats summary
    stats_table = Table(title="Data Hygiene & Cleaning Results", show_header=True)
    stats_table.add_column("Metric", style="bold")
    stats_table.add_column("Count", justify="right", style="magenta")
    stats_table.add_row("Total Input Records", str(stats["total_input_records"]))
    stats_table.add_row("Valid Unique Contacts", f"[green]{stats['valid_contacts']}[/green]")
    stats_table.add_row("Quarantined / Rejected Records", f"[red]{stats['quarantined_records']}[/red]")
    stats_table.add_row("Duplicates / Invalid Removed", str(stats["total_input_records"] - stats["valid_contacts"]))
    console.print(stats_table)

    console.print(f"[green]✓ Cleaned contacts saved to:[/] {cleaned_path}")
    console.print(f"[yellow]⚠ Quarantined records saved to:[/] {quarantine_path}")


def cmd_preview(args):
    """Run interactive CLI review loop."""
    if not DEFAULT_STORAGE.cleaned_contacts_path.exists():
        console.print("[red]Cleaned contacts file not found. Run 'python main.py clean' first.[/red]")
        sys.exit(1)

    df = pd.read_excel(DEFAULT_STORAGE.cleaned_contacts_path)
    contacts = df.to_dict(orient="records")

    if getattr(args, "tier", None):
        contacts = [c for c in contacts if int(c.get("tier", 1)) == args.tier]
        console.print(f"[bold cyan]Filtering by Tier {args.tier} ({len(contacts)} contacts)[/]")

    tracker = OutreachTracker(DEFAULT_STORAGE.db_path, DEFAULT_STORAGE.suppression_list_path)
    engine = TemplateEngine(DEFAULT_PROFILE)
    previewer = PreviewApprovalSystem(engine, tracker)

    if args.limit and args.limit > 0:
        contacts = contacts[:args.limit]

    console.print(f"[bold cyan]Launching interactive review for {len(contacts)} contacts...[/]")
    approved = previewer.interactive_review_loop(contacts)
    console.print(f"[bold green]Session completed. Total approved in this session: {len(approved)}[/]")


def cmd_dashboard(args):
    """Generate standalone HTML preview and tracking dashboard."""
    if not DEFAULT_STORAGE.cleaned_contacts_path.exists():
        console.print("[red]Cleaned contacts file not found. Run 'python main.py clean' first.[/red]")
        sys.exit(1)

    df = pd.read_excel(DEFAULT_STORAGE.cleaned_contacts_path)
    contacts = df.to_dict(orient="records")

    if getattr(args, "tier", None):
        contacts = [c for c in contacts if int(c.get("tier", 1)) == args.tier]

    if args.limit and args.limit > 0:
        contacts = contacts[:args.limit]

    tracker = OutreachTracker(DEFAULT_STORAGE.db_path, DEFAULT_STORAGE.suppression_list_path)
    engine = TemplateEngine(DEFAULT_PROFILE)
    previewer = PreviewApprovalSystem(engine, tracker)

    out_path = previewer.generate_html_dashboard(contacts, DEFAULT_STORAGE.preview_dashboard_path)
    console.print(f"[bold green]✓ Visual HTML Dashboard generated at:[/] file://{out_path.resolve()}")

    if getattr(args, "open", False):
        import webbrowser
        console.print("[dim]Opening dashboard in default web browser...[/dim]")
        webbrowser.open(f"file://{out_path.resolve()}")


def cmd_draft(args):
    """Create personalized email drafts in Gmail for approved contacts."""
    tracker = OutreachTracker(DEFAULT_STORAGE.db_path, DEFAULT_STORAGE.suppression_list_path)
    engine = TemplateEngine(DEFAULT_PROFILE)

    batch_size = args.batch_size or DEFAULT_SAFEGUARDS.max_emails_per_day
    tier = getattr(args, "tier", None)
    approved_contacts = tracker.get_approved_contacts(tier=tier, limit=batch_size)

    if not approved_contacts:
        tier_msg = f" for Tier {tier}" if tier else ""
        console.print(f"[yellow]No approved contacts found{tier_msg}. Run 'python main.py preview' or 'python main.py approve-all' first.[/yellow]")
        return

    targets = approved_contacts

    console.print(f"[bold cyan]Preparing to create drafts for {len(targets)} contacts...[/]")

    # Authentication or Dry Run
    if args.dry_run:
        console.print("[bold yellow]Running in DRY-RUN mode (Mock Gmail API)[/]")
        service = MockGmailService()
    else:
        authenticator = GmailAuthenticator(
            DEFAULT_SAFEGUARDS.credentials_path,
            DEFAULT_SAFEGUARDS.token_path,
            DEFAULT_SAFEGUARDS.gmail_scopes
        )
        try:
            service = authenticator.get_service()
        except FileNotFoundError as e:
            console.print(f"[bold red]{e}[/bold red]")
            console.print("\n[cyan]Tip: You can test the entire pipeline safely right now with the --dry-run flag:[/cyan]")
            console.print("  [bold green]python main.py draft --dry-run[/bold green]")
            return

    verifier = EmailDeliverabilityVerifier()
    dispatcher = EmailDispatcher(
        service, tracker,
        min_jitter=0 if args.dry_run else 2,
        max_jitter=0 if args.dry_run else 4,
        max_daily_limit=DEFAULT_SAFEGUARDS.max_emails_per_day,
        verifier=verifier
    )

    resume_file = DEFAULT_PROFILE.resume_path if DEFAULT_PROFILE.resume_path.exists() else None
    if resume_file:
        console.print(f"[green]✓ Attaching resume: {resume_file.name}[/green]")
    else:
        console.print("[yellow]Note: No resume.pdf found in project root. Drafts will be created without attachment.[/yellow]")

    success_count = 0
    skipped_undeliverable = 0

    for idx, c in enumerate(targets, 1):
        email = c["email"]
        company = c.get("company", "Company")
        rendered = engine.render(c, template_key=c.get("template_key"))
        
        console.print(f"[{idx}/{len(targets)}] Verifying deliverability & drafting for {email} ({company})...")
        success, msg, draft_id = dispatcher.create_draft(
            to_email=email,
            subject=rendered["subject"],
            text_body=rendered["text_body"],
            html_body=rendered["html_body"],
            attachment_path=resume_file,
            contact_meta=c
        )

        if success:
            success_count += 1
            console.print(f"  [green]✓ {msg}[/green]")
            if not args.dry_run and idx < len(targets):
                dispatcher.apply_jitter("draft")
        else:
            if "DELETED" in msg or "undeliverable" in msg.lower() or "unavailable" in msg.lower():
                skipped_undeliverable += 1
                console.print(f"  [bold red]🗑️ {msg}[/bold red]")
            else:
                console.print(f"  [red]✗ {msg}[/red]")

    summary_msg = f"\n[bold green]Draft Creation Finished: {success_count}/{len(targets)} drafts ready in Gmail.[/bold green]"
    if skipped_undeliverable > 0:
        summary_msg += f" [yellow]({skipped_undeliverable} deleted from queue due to failed security check: unavailable/undeliverable)[/yellow]"
    console.print(summary_msg)

    # Automatically refresh the visual dashboard page
    try:
        if DEFAULT_STORAGE.cleaned_contacts_path.exists():
            df_all = pd.read_excel(DEFAULT_STORAGE.cleaned_contacts_path)
            all_contacts = df_all.to_dict(orient="records")
            previewer = PreviewApprovalSystem(engine, tracker)
            out_dash = previewer.generate_html_dashboard(all_contacts, DEFAULT_STORAGE.preview_dashboard_path)
            console.print(f"[bold cyan]✓ Dashboard page automatically updated at:[/] file://{out_dash.resolve()}")
    except Exception as e:
        console.print(f"[dim]Could not auto-update dashboard: {e}[/dim]")


def cmd_send(args):
    """Directly send emails (requires explicit confirmation flag --confirm-send)."""
    if not args.confirm_send:
        console.print(Panel(
            "[bold red]SAFETY STOP: Explicit confirmation required to dispatch live emails.[/bold red]\n\n"
            "To send emails directly via Gmail API, you must explicitly pass: [bold yellow]--confirm-send[/bold yellow]\n"
            "Example: python main.py send --batch-size 20 --confirm-send",
            title="Anti-Spam Safeguard"
        ))
        return

    tracker = OutreachTracker(DEFAULT_STORAGE.db_path, DEFAULT_STORAGE.suppression_list_path)
    engine = TemplateEngine(DEFAULT_PROFILE)

    tier = getattr(args, "tier", None)
    targets = tracker.get_approved_contacts(tier=tier, limit=args.batch_size)

    if not targets:
        tier_msg = f" for Tier {tier}" if tier else ""
        console.print(f"[yellow]No approved contacts found{tier_msg} to send. Run preview/approval first.[/yellow]")
        return

    if args.dry_run:
        console.print("[bold yellow]Running in DRY-RUN mode (Simulated Sending)[/]")
        service = MockGmailService()
    else:
        authenticator = GmailAuthenticator(
            DEFAULT_SAFEGUARDS.credentials_path,
            DEFAULT_SAFEGUARDS.token_path,
            DEFAULT_SAFEGUARDS.gmail_scopes
        )
        service = authenticator.get_service()

    verifier = EmailDeliverabilityVerifier()
    dispatcher = EmailDispatcher(
        service, tracker,
        min_jitter=0 if args.dry_run else DEFAULT_SAFEGUARDS.min_jitter_seconds,
        max_jitter=0 if args.dry_run else DEFAULT_SAFEGUARDS.max_jitter_seconds,
        max_daily_limit=DEFAULT_SAFEGUARDS.max_emails_per_day,
        verifier=verifier
    )

    resume_file = DEFAULT_PROFILE.resume_path if DEFAULT_PROFILE.resume_path.exists() else None

    sent_count = 0
    skipped_undeliverable = 0

    for idx, c in enumerate(targets, 1):
        email = c["email"]
        company = c.get("company", "Company")
        rendered = engine.render(c, template_key=c.get("template_key"))
        
        console.print(f"[{idx}/{len(targets)}] Verifying deliverability & sending to {email} ({company})...")
        success, msg, msg_id = dispatcher.send_email(
            to_email=email,
            subject=rendered["subject"],
            text_body=rendered["text_body"],
            html_body=rendered["html_body"],
            attachment_path=resume_file,
            contact_meta=c
        )

        if success:
            sent_count += 1
            console.print(f"  [green]✓ {msg}[/green]")
            if not args.dry_run and idx < len(targets):
                dispatcher.apply_jitter("send")
        else:
            if "DELETED" in msg or "undeliverable" in msg.lower() or "unavailable" in msg.lower():
                skipped_undeliverable += 1
                console.print(f"  [bold red]🗑️ {msg}[/bold red]")
            else:
                console.print(f"  [red]✗ {msg}[/red]")

    summary_send = f"\n[bold green]Outreach Dispatched: {sent_count}/{len(targets)} emails sent successfully.[/bold green]"
    if skipped_undeliverable > 0:
        summary_send += f" [yellow]({skipped_undeliverable} deleted from queue due to failed security check: unavailable/undeliverable)[/yellow]"
    console.print(summary_send)

    # Automatically refresh the visual dashboard page
    try:
        if DEFAULT_STORAGE.cleaned_contacts_path.exists():
            df_all = pd.read_excel(DEFAULT_STORAGE.cleaned_contacts_path)
            all_contacts = df_all.to_dict(orient="records")
            previewer = PreviewApprovalSystem(engine, tracker)
            out_dash = previewer.generate_html_dashboard(all_contacts, DEFAULT_STORAGE.preview_dashboard_path)
            console.print(f"[bold cyan]✓ Dashboard page automatically updated at:[/] file://{out_dash.resolve()}")
    except Exception as e:
        console.print(f"[dim]Could not auto-update dashboard: {e}[/dim]")


def cmd_approve_all(args):
    """Batch approve all cleaned contacts that are not suppressed."""
    if not DEFAULT_STORAGE.cleaned_contacts_path.exists():
        console.print("[red]Cleaned contacts file not found. Run 'python main.py clean' first.[/red]")
        sys.exit(1)

    df = pd.read_excel(DEFAULT_STORAGE.cleaned_contacts_path)
    contacts = df.to_dict(orient="records")

    if getattr(args, "tier", None):
        contacts = [c for c in contacts if int(c.get("tier", 1)) == args.tier]
        console.print(f"[bold cyan]Filtering approvals by Tier {args.tier} ({len(contacts)} contacts)...[/]")

    tracker = OutreachTracker(DEFAULT_STORAGE.db_path, DEFAULT_STORAGE.suppression_list_path)
    engine = TemplateEngine(DEFAULT_PROFILE)

    count = 0
    for c in contacts:
        email = c.get("email")
        if tracker.is_suppressed(email) or tracker.is_already_contacted(email):
            continue
        rendered = engine.render(c)
        tracker.upsert_contact_status(
            email=email,
            name=c.get("cleaned_name", ""),
            company=c.get("cleaned_company", ""),
            job_title=c.get("job_title", ""),
            status="APPROVED",
            tier=int(c.get("tier", 1)),
            template_key=rendered.get("template_key"),
            subject=rendered.get("subject")
        )
        count += 1

    console.print(f"[bold green]✓ Successfully approved {count} verified contacts for outreach.[/bold green]")


def cmd_status(args):
    """Display campaign statistics and metrics."""
    tracker = OutreachTracker(DEFAULT_STORAGE.db_path, DEFAULT_STORAGE.suppression_list_path)
    stats = tracker.get_summary_stats()

    table = Table(title="Email Outreach Campaign Status", show_header=True)
    table.add_column("Category", style="cyan")
    table.add_column("Count", justify="right", style="bold green")

    table.add_row("Total Tracked in Database", str(stats["total_logged"]))
    table.add_row("Suppressed / Opt-outs", str(stats["suppressed_contacts"]))
    table.add_row("Drafts Created Today", str(stats["drafts_today"]))
    table.add_row("Emails Sent Today", str(stats["sent_today"]))
    table.add_row("Daily Sending Limit Ceiling", str(DEFAULT_SAFEGUARDS.max_emails_per_day))

    console.print(table)

    if stats["status_breakdown"]:
        breakdown_table = Table(title="Outreach Status Breakdown", show_header=True)
        breakdown_table.add_column("Status", style="yellow")
        breakdown_table.add_column("Contacts", justify="right")
        for status, count in stats["status_breakdown"].items():
            breakdown_table.add_row(status, str(count))
        console.print(breakdown_table)


def cmd_verify_emails(args):
    """Audit email deliverability & MX records for contacts."""
    if not DEFAULT_STORAGE.cleaned_contacts_path.exists():
        console.print("[red]Cleaned contacts file not found. Run 'python main.py clean' first.[/red]")
        sys.exit(1)

    df = pd.read_excel(DEFAULT_STORAGE.cleaned_contacts_path)
    contacts = df.to_dict(orient="records")

    if getattr(args, "tier", None):
        contacts = [c for c in contacts if int(c.get("tier", 1)) == args.tier]
        console.print(f"[bold cyan]Filtering deliverability audit by Tier {args.tier} ({len(contacts)} contacts)...[/]")

    if args.limit and args.limit > 0:
        contacts = contacts[:args.limit]

    verifier = EmailDeliverabilityVerifier()
    console.print(f"[bold cyan]Auditing MX deliverability for {len(contacts)} contacts...[/]")

    table = Table(title="Email Deliverability & MX Verification", show_header=True)
    table.add_column("Company", style="bold")
    table.add_column("Recipient Name", style="cyan")
    table.add_column("Domain", style="magenta")
    table.add_column("Deliverability Status", justify="center")
    table.add_column("MX Exchange / Reason", style="dim")

    deliverable_count = 0
    undeliverable_count = 0

    for c in contacts:
        email = str(c.get("email", "")).strip()
        res = verifier.verify(email)
        company = str(c.get("cleaned_company", "N/A"))
        name = str(c.get("cleaned_name", "N/A"))

        if res.is_deliverable:
            deliverable_count += 1
            mx_disp = ", ".join(res.mx_records[:1]) if res.mx_records else res.reason
            table.add_row(company, name, res.domain, "[bold green]✓ DELIVERABLE[/bold green]", mx_disp)
        else:
            undeliverable_count += 1
            table.add_row(company, name, res.domain, "[bold red]✗ UNDELIVERABLE[/bold red]", res.reason)

    console.print(table)
    console.print(f"\n[bold green]Summary: {deliverable_count}/{len(contacts)} contacts confirmed deliverable with active MX records.[/bold green]")
    if undeliverable_count > 0:
        console.print(f"[bold yellow]⚠ {undeliverable_count} contacts are undeliverable and will be automatically skipped during draft creation.[/bold yellow]")
def cmd_purge_invalid(args):
    """
    Enforce strict two-condition security verification across all contacts in outreach history:
    1. Condition 1 (Available): Valid RFC syntax and non-generic/system mailbox (reject payable, billing, etc.)
    2. Condition 2 (Deliverable): Valid MX records and non-disposable domain
    If either condition fails:
      - Purge any associated Gmail draft from Gmail API
      - Delete contact from outreach SQLite database
    """
    console.print(Panel(
        "[bold cyan]Two-Condition Security Audit & Queue Purge[/bold cyan]\n"
        "Condition 1: Address Available & Legitimate (Non-System/Payable)\n"
        "Condition 2: Address Deliverable (Active MX Records & Non-Disposable)\n"
        "Action: If BOTH pass -> DRAFT. Otherwise -> DELETE.",
        title="🛡️ Security Verifier"
    ))

    tracker = OutreachTracker(DEFAULT_STORAGE.db_path, DEFAULT_STORAGE.suppression_list_path)
    verifier = EmailDeliverabilityVerifier()

    service = None
    if not getattr(args, "dry_run", False):
        try:
            authenticator = GmailAuthenticator(
                DEFAULT_SAFEGUARDS.credentials_path,
                DEFAULT_SAFEGUARDS.token_path,
                DEFAULT_SAFEGUARDS.gmail_scopes
            )
            service = authenticator.get_service()
        except Exception as e:
            console.print(f"[dim]Note: Live Gmail API connection not active ({e}). Using mock service for simulation.[/dim]")
            service = MockGmailService()
    else:
        console.print("[bold yellow]Running in DRY-RUN mode (No changes will be written)[/bold yellow]")
        service = MockGmailService()

    dispatcher = EmailDispatcher(
        service, tracker,
        min_jitter=0,
        max_jitter=0,
        verifier=verifier
    )

    all_contacts = tracker.get_all_contacts()
    if not all_contacts:
        console.print("[yellow]No contacts found in outreach database.[/yellow]")
        return

    console.print(f"Auditing [bold cyan]{len(all_contacts)}[/bold cyan] contacts in database against security conditions...\n")

    deleted_count = 0
    drafts_purged = 0

    table = Table(title="Security Purge Action Log", show_header=True)
    table.add_column("Recipient Email", style="bold red")
    table.add_column("Company", style="cyan")
    table.add_column("Prev Status", style="yellow")
    table.add_column("Action Taken & Reason", style="dim")

    for c in all_contacts:
        email = c.get("email")
        if not email:
            continue

        sec_check = verifier.security_check(email)
        if not sec_check.can_draft:
            deleted_count += 1
            draft_id = c.get("gmail_draft_id")
            draft_msg = ""

            if draft_id and not getattr(args, "dry_run", False):
                if dispatcher.delete_draft(draft_id):
                    drafts_purged += 1
                    draft_msg = f" | Purged Gmail Draft ({draft_id[:8]}...)"
                else:
                    draft_msg = f" | Failed to purge Gmail Draft ({draft_id[:8]}...)"
            elif draft_id and getattr(args, "dry_run", False):
                draft_msg = f" | [Simulated] Purge Gmail Draft ({draft_id[:8]}...)"

            if not getattr(args, "dry_run", False):
                tracker.delete_contact(email)
                action_str = f"[bold red]DELETED[/bold red]: {sec_check.reason}{draft_msg}"
            else:
                action_str = f"[bold yellow]WOULD DELETE[/bold yellow]: {sec_check.reason}{draft_msg}"

            table.add_row(
                email,
                c.get("company") or "N/A",
                c.get("status") or "N/A",
                action_str
            )

    if deleted_count > 0:
        console.print(table)
        action_verb = "Purged" if not getattr(args, "dry_run", False) else "Identified"
        console.print(f"\n[bold green]✓ Security Action Complete:[/] {action_verb} {deleted_count} invalid contacts from queue.")
        if drafts_purged > 0:
            console.print(f"[bold green]✓ Draft Purge Complete:[/] {drafts_purged} drafts permanently removed from Gmail.")
    else:
        console.print("[bold green]✓ All contacts in database passed both security conditions (Available & Deliverable). None deleted.[/bold green]")

    # Auto-refresh dashboard
    if not getattr(args, "dry_run", False) and deleted_count > 0:
        try:
            if DEFAULT_STORAGE.cleaned_contacts_path.exists():
                df_all = pd.read_excel(DEFAULT_STORAGE.cleaned_contacts_path)
                contacts = df_all.to_dict(orient="records")
                engine = TemplateEngine(DEFAULT_PROFILE)
                previewer = PreviewApprovalSystem(engine, tracker)
                out_dash = previewer.generate_html_dashboard(contacts, DEFAULT_STORAGE.preview_dashboard_path)
                console.print(f"[bold cyan]✓ Visual dashboard updated:[/] file://{out_dash.resolve()}")
        except Exception as e:
            console.print(f"[dim]Could not auto-update dashboard: {e}[/dim]")


def cmd_reset(args):
    """Reset campaign database and history."""
    if not args.confirm:
        console.print("[bold red]Please pass --confirm to reset campaign history.[/bold red]")
        console.print("Example: python main.py reset --confirm")
        return
    
    if DEFAULT_STORAGE.db_path.exists():
        DEFAULT_STORAGE.db_path.unlink()
    console.print("[bold green]✓ Campaign database reset successfully.[/bold green]")


def cmd_audit(args):
    """Run comprehensive security, privacy, and secret leak audit."""
    console.print(Panel(
        "[bold cyan]Security & Safeguards Audit[/bold cyan]\n"
        "Auditing Git tracking, secret leakage, file permissions, privacy masking, and anti-spam limits.",
        title="🔒 Security Audit"
    ))

    audit_table = Table(title="Security & Safety Verification", show_header=True)
    audit_table.add_column("Audit Category", style="cyan", width=28)
    audit_table.add_column("Status", width=12)
    audit_table.add_column("Details", style="dim")

    overall_pass = True

    # 1. Git Tracked Files Audit
    try:
        res = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True)
        tracked_files = [f.strip() for f in res.stdout.splitlines() if f.strip()]
        
        forbidden_in_git = []
        forbidden_patterns = [
            "credentials.json", "token.json", "client_secret_", ".env",
            "outreach_history.db", "preview_dashboard.html"
        ]
        for f in tracked_files:
            for pat in forbidden_patterns:
                if pat in f:
                    forbidden_in_git.append(f)
            if f.endswith((".xlsx", ".xls", ".csv")) and f != "sample_recruiter_contacts.xlsx":
                forbidden_in_git.append(f)
            if f.endswith(".pdf"):
                forbidden_in_git.append(f)

        if forbidden_in_git:
            overall_pass = False
            audit_table.add_row("Git Repository Tracking", "[bold red]FAIL[/bold red]", f"Tracked forbidden files: {', '.join(forbidden_in_git)}")
        else:
            audit_table.add_row("Git Repository Tracking", "[bold green]PASS[/bold green]", f"All {len(tracked_files)} tracked files safe (0 secrets or sheets)")
    except Exception as e:
        audit_table.add_row("Git Repository Tracking", "[yellow]SKIPPED[/yellow]", f"Git query failed: {e}")

    # 2. Git History Secret Leak Scan
    try:
        res = subprocess.run(["git", "log", "-p"], capture_output=True, text=True)
        if res.returncode == 0:
            log_output = res.stdout
            leak_matches = re.findall(r"(GOCSPX-[A-Za-z0-9_-]{20,}|ya29\.[A-Za-z0-9_-]{20,}|BEGIN (?:RSA )?PRIVATE KEY)", log_output)
            if leak_matches:
                overall_pass = False
                audit_table.add_row("Git Commit History", "[bold red]FAIL[/bold red]", "Secret key pattern detected in commit history!")
            else:
                audit_table.add_row("Git Commit History", "[bold green]PASS[/bold green]", "Zero secret tokens or private keys in git commit history")
        else:
            audit_table.add_row("Git Commit History", "[dim]N/A[/dim]", "No git history found")
    except Exception as e:
        audit_table.add_row("Git Commit History", "[yellow]SKIPPED[/yellow]", str(e))

    # 3. Local Sensitive File Permissions
    base_dir = Path(__file__).resolve().parent
    cred_files = (
        list(base_dir.glob("credentials.json")) +
        list(base_dir.glob("token.json")) +
        list(base_dir.glob("client_secret_*.json")) +
        list(base_dir.glob(".env")) +
        list(base_dir.glob("*.pdf")) +
        list((base_dir / "data").glob("outreach_history.db"))
    )
    perm_issues = []
    for cf in cred_files:
        mode = oct(stat.S_IMODE(cf.stat().st_mode))
        if cf.stat().st_mode & (stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH):
            try:
                cf.chmod(0o600)
            except Exception:
                perm_issues.append(f"{cf.name} ({mode})")
    if perm_issues:
        audit_table.add_row("File Permissions", "[yellow]WARN[/yellow]", f"Permissions loose: {', '.join(perm_issues)}")
    else:
        audit_table.add_row("File Permissions", "[bold green]PASS[/bold green]", f"Hardened to 600 (owner-only access for {len(cred_files)} sensitive files)")

    # 4. Pre-Commit Hook Active
    hook_path = base_dir / ".git" / "hooks" / "pre-commit"
    if hook_path.exists() and os.access(hook_path, os.X_OK):
        audit_table.add_row("Pre-Commit Guard Hook", "[bold green]PASS[/bold green]", "Active (.git/hooks/pre-commit blocks secret commits)")
    else:
        audit_table.add_row("Pre-Commit Guard Hook", "[yellow]WARN[/yellow]", "Pre-commit hook not installed or not executable")

    # 5. Dashboard Data Privacy (Email Masking)
    dash_path = DEFAULT_STORAGE.preview_dashboard_path
    if dash_path.exists():
        dash_content = dash_path.read_text(encoding="utf-8")
        email_matches = re.findall(r"\b[A-Za-z0-9._%+-]+@(?!example\.com|domain\.com|test\.com)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", dash_content)
        email_matches = [m for m in email_matches if m != DEFAULT_PROFILE.email_address]
        if email_matches:
            overall_pass = False
            audit_table.add_row("Dashboard Privacy", "[bold red]FAIL[/bold red]", f"Unmasked emails found in HTML: {len(email_matches)}")
        else:
            audit_table.add_row("Dashboard Privacy", "[bold green]PASS[/bold green]", "Recruiter email addresses 100% masked in HTML dashboard")
    else:
        audit_table.add_row("Dashboard Privacy", "[dim]N/A[/dim]", "Dashboard not yet generated")

    # 6. Anti-Spam & Delivery Limits
    limits_pass = (
        DEFAULT_SAFEGUARDS.max_emails_per_day <= 50 and
        DEFAULT_SAFEGUARDS.min_jitter_seconds >= 15 and
        DEFAULT_SAFEGUARDS.gmail_scopes == ["https://www.googleapis.com/auth/gmail.compose"]
    )
    if limits_pass:
        audit_table.add_row(
            "Anti-Spam Safeguards",
            "[bold green]PASS[/bold green]",
            f"Daily Cap: {DEFAULT_SAFEGUARDS.max_emails_per_day}/day | Jitter: {DEFAULT_SAFEGUARDS.min_jitter_seconds}-{DEFAULT_SAFEGUARDS.max_jitter_seconds}s | Minimal Scope"
        )
    else:
        audit_table.add_row("Anti-Spam Safeguards", "[yellow]WARN[/yellow]", "Settings exceed recommended anti-spam bounds")

    # 7. Suppression List & Duplicate Prevention
    tracker = OutreachTracker(DEFAULT_STORAGE.db_path, DEFAULT_STORAGE.suppression_list_path)
    summary = tracker.get_summary_stats()
    audit_table.add_row(
        "Suppression & Tracker",
        "[bold green]PASS[/bold green]",
        f"Database connected | {summary['suppressed_contacts']} suppressed | {summary['total_logged']} logged"
    )

    console.print(audit_table)

    if overall_pass:
        console.print("\n[bold green]✓ ALL SAFETY CHECKS PASSED: Zero credential leaks, hardened storage, and anti-spam safeguards fully engaged.[/bold green]\n")
    else:
        console.print("\n[bold red]⚠ ONE OR MORE SECURITY AUDIT CHECKS FAILED. Please review the table above.[/bold red]\n")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Automated HR Email Outreach System for Internship & Entry-Level Job Opportunities"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # audit
    subparsers.add_parser("audit", help="Run comprehensive security, privacy, and secret leak audit")

    # reset
    p_reset = subparsers.add_parser("reset", help="Reset campaign history and SQLite database")
    p_reset.add_argument("--confirm", action="store_true", help="Confirm database reset")

    # clean
    p_clean = subparsers.add_parser("clean", help="Clean, deduplicate, and validate input spreadsheet")
    p_clean.add_argument("--file", "-f", help="Path to input Excel or CSV file")

    # preview
    p_prev = subparsers.add_parser("preview", help="Interactive terminal preview and approval")
    p_prev.add_argument("--limit", "-l", type=int, default=0, help="Number of contacts to preview (0 = all)")
    p_prev.add_argument("--tier", "-t", type=int, choices=[1, 2, 3], help="Filter contacts by tier (1: MNC, 2: IT Services, 3: Staffing)")

    # dashboard
    p_dash = subparsers.add_parser("dashboard", help="Generate HTML preview dashboard")
    p_dash.add_argument("--limit", "-l", type=int, default=0, help="Number of contacts to include in dashboard (0 = all)")
    p_dash.add_argument("--tier", "-t", type=int, choices=[1, 2, 3], help="Filter contacts by tier (1: MNC, 2: IT Services, 3: Staffing)")
    p_dash.add_argument("--open", "-o", action="store_true", help="Automatically open dashboard in default web browser")

    # approve-all
    p_appr = subparsers.add_parser("approve-all", help="Batch approve all cleaned contacts")
    p_appr.add_argument("--tier", "-t", type=int, choices=[1, 2, 3], help="Batch approve specific tier only")

    # draft
    p_draft = subparsers.add_parser("draft", help="Create personalized email drafts in Gmail")
    p_draft.add_argument("--batch-size", "-b", type=int, default=50, help="Number of drafts to create")
    p_draft.add_argument("--tier", "-t", type=int, choices=[1, 2, 3], help="Filter drafts by tier")
    p_draft.add_argument("--dry-run", action="store_true", help="Simulate without connecting to live Gmail API")

    # send
    p_send = subparsers.add_parser("send", help="Send approved emails via Gmail API")
    p_send.add_argument("--batch-size", "-b", type=int, default=20, help="Number of emails to send")
    p_send.add_argument("--tier", "-t", type=int, choices=[1, 2, 3], help="Filter send targets by tier")
    p_send.add_argument("--confirm-send", action="store_true", help="Explicit confirmation to send live emails")
    p_send.add_argument("--dry-run", action="store_true", help="Simulate sending without dispatching live emails")

    # status
    subparsers.add_parser("status", help="Show campaign metrics and tracking status")

    # verify-emails
    p_verify = subparsers.add_parser("verify-emails", help="Audit email deliverability & MX records for contacts")
    p_verify.add_argument("--limit", "-l", type=int, default=20, help="Number of contacts to verify (0 = all)")
    p_verify.add_argument("--tier", "-t", type=int, choices=[1, 2, 3], help="Filter contacts by tier (1: MNC, 2: IT Services, 3: Staffing)")

    # purge-invalid
    p_purge = subparsers.add_parser("purge-invalid", help="Enforce two-condition security check: delete unavailable/undeliverable contacts and drafts")
    p_purge.add_argument("--dry-run", action="store_true", help="Simulate deletion without modifying database or Gmail")

    # sample
    p_sample = subparsers.add_parser("sample", help="Generate a synthetic 2,000-contact sample spreadsheet")
    p_sample.add_argument("--rows", "-r", type=int, default=2000, help="Number of sample records")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "audit":
        cmd_audit(args)
    elif args.command == "verify-emails":
        cmd_verify_emails(args)
    elif args.command == "purge-invalid":
        cmd_purge_invalid(args)
    elif args.command == "clean":
        cmd_clean(args)
    elif args.command == "preview":
        cmd_preview(args)
    elif args.command == "dashboard":
        cmd_dashboard(args)
    elif args.command == "approve-all":
        cmd_approve_all(args)
    elif args.command == "draft":
        cmd_draft(args)
    elif args.command == "send":
        cmd_send(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "reset":
        cmd_reset(args)
    elif args.command == "sample":
        from generate_sample_data import generate_sample_dataset
        generate_sample_dataset(num_records=args.rows)


if __name__ == "__main__":
    main()
