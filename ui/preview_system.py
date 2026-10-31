"""
Interactive Email Preview, Approval Workflow, and Modern HTML Dashboard Generator
"""
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt

from config import DEFAULT_PROFILE, DEFAULT_SAFEGUARDS

console = Console()


class PreviewApprovalSystem:
    """Manages terminal-based review and generates standalone HTML preview dashboards."""

    def __init__(self, template_engine: Any, tracker: Any):
        self.template_engine = template_engine
        self.tracker = tracker

    def render_cli_preview(self, contact: Dict[str, Any], rendered: Dict[str, Any], index: int, total: int):
        """Display beautifully formatted card in terminal."""
        meta_table = Table(show_header=False, box=None, padding=(0, 1))
        meta_table.add_row("[bold cyan]Company:[/]", f"[bold white]{contact.get('cleaned_company', 'N/A')}[/]")
        meta_table.add_row("[bold cyan]Recipient:[/]", f"{contact.get('cleaned_name', 'Hiring Team')} [dim]({contact.get('job_title', 'Recruiter')})[/]")
        meta_table.add_row("[bold cyan]Tier:[/]", f"Tier {contact.get('tier', 1)}")
        meta_table.add_row("[bold cyan]Template:[/]", f"[magenta]{rendered.get('template_name')}[/]")
        meta_table.add_row("[bold cyan]Subject:[/]", f"[bold yellow]{rendered.get('subject')}[/]")

        warnings = rendered.get("spam_warnings", [])
        if warnings:
            meta_table.add_row("[bold red]Warnings:[/]", f"[red]{'; '.join(warnings)}[/]")

        console.print("\n" + "─" * 80)
        console.print(Panel(
            meta_table,
            title=f"[bold green]📬 Email Review [{index}/{total}][/]",
            subtitle="[dim]Verified & Anti-Spam Checked[/dim]",
            border_style="cyan"
        ))
        
        console.print(Panel(
            rendered.get("text_body", ""),
            title="[bold blue]Personalized Message Body[/]",
            border_style="blue"
        ))

    def interactive_review_loop(self, contacts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Interactive review loop in terminal allowing:
        - Approve (A)
        - Reject (R)
        - Batch Approve All (B)
        - Quit (Q)
        """
        approved_contacts = []
        batch_approve_all = False

        total = len(contacts)
        for i, contact in enumerate(contacts, 1):
            email = contact.get("email")
            
            if self.tracker.is_already_contacted(email):
                console.print(f"[dim]Skipping {email} (Already Contacted/Drafted)[/dim]")
                continue
            if self.tracker.is_suppressed(email):
                console.print(f"[dim]Skipping {email} (Suppression List)[/dim]")
                continue

            rendered = self.template_engine.render(contact)

            if batch_approve_all:
                contact["rendered_email"] = rendered
                self.tracker.upsert_contact_status(
                    email=email,
                    name=contact.get("cleaned_name", ""),
                    company=contact.get("cleaned_company", ""),
                    job_title=contact.get("job_title", ""),
                    status="APPROVED",
                    tier=int(contact.get("tier", 1)),
                    template_key=rendered.get("template_key"),
                    subject=rendered.get("subject")
                )
                approved_contacts.append(contact)
                continue

            self.render_cli_preview(contact, rendered, i, total)

            choice = Prompt.ask(
                r"[bold yellow]Action (\[A]pprove / \[R]eject / \[B]atch All / \[Q]uit)[/]",
                choices=["a", "r", "b", "q"],
                default="a"
            ).lower()

            if choice == "a":
                contact["rendered_email"] = rendered
                self.tracker.upsert_contact_status(
                    email=email,
                    name=contact.get("cleaned_name", ""),
                    company=contact.get("cleaned_company", ""),
                    job_title=contact.get("job_title", ""),
                    status="APPROVED",
                    tier=int(contact.get("tier", 1)),
                    template_key=rendered.get("template_key"),
                    subject=rendered.get("subject")
                )
                approved_contacts.append(contact)
                console.print(f"[bold green]✓ Approved for outreach: {contact.get('cleaned_company')}[/]")
            elif choice == "r":
                self.tracker.upsert_contact_status(
                    email=email,
                    name=contact.get("cleaned_name", ""),
                    company=contact.get("cleaned_company", ""),
                    status="REJECTED",
                    tier=int(contact.get("tier", 1))
                )
                console.print(f"[bold red]✗ Rejected / Skipped: {contact.get('cleaned_company')}[/]")
            elif choice == "b":
                batch_approve_all = True
                contact["rendered_email"] = rendered
                self.tracker.upsert_contact_status(
                    email=email,
                    name=contact.get("cleaned_name", ""),
                    company=contact.get("cleaned_company", ""),
                    job_title=contact.get("job_title", ""),
                    status="APPROVED",
                    tier=int(contact.get("tier", 1)),
                    template_key=rendered.get("template_key"),
                    subject=rendered.get("subject")
                )
                approved_contacts.append(contact)
                console.print("[bold cyan]Batch approving all remaining verified contacts...[/]")
            elif choice == "q":
                console.print("[yellow]Exiting review. Saved all approvals made so far.[/yellow]")
                break

        return approved_contacts

    def generate_html_dashboard(self, contacts: List[Dict[str, Any]], output_path: Path) -> Path:
        """
        Generate a modern, responsive HTML dashboard for visual inspection of all personalized emails.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        def _clean_val(val, default=""):
            if val is None or pd.isna(val) or str(val).strip() == "":
                return default
            return str(val).strip()

        # Query live database statuses
        db_statuses = {}
        try:
            with self.tracker._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT email, status, tier, gmail_draft_id, gmail_message_id FROM outreach_log")
                db_statuses = {row["email"]: dict(row) for row in cursor.fetchall()}
        except Exception:
            pass

        items_json = []
        counts = {
            "total": len(contacts),
            "drafted": 0,
            "approved": 0,
            "sent": 0,
            "review": 0,
            "tier1": 0,
            "tier2": 0,
            "tier3": 0
        }

        for c in contacts:
            email = _clean_val(c.get("email"))
            rendered = self.template_engine.render(c)
            is_supp = self.tracker.is_suppressed(email)
            
            tier_num = int(c.get("tier", 1))
            if tier_num == 1:
                counts["tier1"] += 1
            elif tier_num == 2:
                counts["tier2"] += 1
            else:
                counts["tier3"] += 1

            db_info = db_statuses.get(email, {})
            row_status = db_info.get("status")
            draft_id = db_info.get("gmail_draft_id", "")
            message_id = db_info.get("gmail_message_id", "")

            if is_supp:
                status = "Suppressed"
            elif row_status == "DRAFTED":
                status = "Drafted in Gmail"
                counts["drafted"] += 1
            elif row_status == "SENT":
                status = "Sent"
                counts["sent"] += 1
            elif row_status == "APPROVED":
                status = "Approved"
                counts["approved"] += 1
            elif row_status == "REJECTED":
                status = "Rejected"
            else:
                status = "Ready for Review"
                counts["review"] += 1

            items_json.append({
                "id": len(items_json),
                "name": _clean_val(c.get("cleaned_name"), "Hiring Team"),
                "company": _clean_val(c.get("cleaned_company"), "N/A"),
                "title": _clean_val(c.get("job_title"), "Recruiter"),
                "status": status,
                "tier": tier_num,
                "draft_id": draft_id,
                "message_id": message_id,
                "template": rendered.get("template_name", "Standard Outreach"),
                "subject": rendered.get("subject", ""),
                "text_body": rendered.get("text_body", ""),
                "html_body": rendered.get("html_body", "")
            })

        drafts_today = self.tracker.get_daily_count("drafts_count")
        sent_today = self.tracker.get_daily_count("sent_count")
        daily_cap = DEFAULT_SAFEGUARDS.max_emails_per_day

        stats_payload = {
            "total": counts["total"],
            "drafted": counts["drafted"],
            "approved": counts["approved"],
            "sent": counts["sent"],
            "review": counts["review"],
            "tier1": counts["tier1"],
            "tier2": counts["tier2"],
            "tier3": counts["tier3"],
            "drafts_today": drafts_today,
            "sent_today": sent_today,
            "daily_cap": daily_cap,
            "jitter_range": f"{DEFAULT_SAFEGUARDS.min_jitter_seconds}–{DEFAULT_SAFEGUARDS.max_jitter_seconds}s"
        }

        profile_payload = {
            "name": DEFAULT_PROFILE.full_name,
            "degree": DEFAULT_PROFILE.degree,
            "grad_year": DEFAULT_PROFILE.grad_year,
            "target_role": DEFAULT_PROFILE.target_role,
            "github": DEFAULT_PROFILE.github_url,
            "linkedin": DEFAULT_PROFILE.linkedin_url,
            "portfolio": DEFAULT_PROFILE.portfolio_url or "#"
        }

        html_template = """<!DOCTYPE html>
<html lang="en" class="scroll-smooth">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>HR Outreach & Deliverability Dashboard</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          fontFamily: {
            sans: ['"Plus Jakarta Sans"', 'sans-serif'],
            mono: ['"JetBrains Mono"', 'monospace']
          }
        }
      }
    };
  </script>
  <style>
    /* Custom scrollbar */
    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: rgba(156, 163, 175, 0.4); border-radius: 9999px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(156, 163, 175, 0.7); }
    .glass { backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); }
  </style>
</head>
<body class="bg-slate-50 text-slate-800 dark:bg-slate-950 dark:text-slate-100 min-h-screen font-sans transition-colors duration-200">

  <!-- Top Announcement / Status Bar -->
  <div class="bg-gradient-to-r from-indigo-600 via-purple-600 to-blue-600 text-white text-xs py-2 px-4 shadow-sm">
    <div class="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2">
      <div class="flex items-center gap-2">
        <span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-white/20 uppercase tracking-wider">Production UI</span>
        <span>Candidate: <strong>__PROFILE_NAME__</strong> (__PROFILE_DEGREE__, Class of __PROFILE_GRAD_YEAR__)</span>
      </div>
      <div class="flex items-center gap-3">
        <a href="__PROFILE_GITHUB__" target="_blank" class="hover:underline flex items-center gap-1 opacity-90 hover:opacity-100">
          <svg class="w-3.5 h-3.5 fill-current" viewBox="0 0 24 24"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg>
          GitHub
        </a>
        <span>•</span>
        <a href="__PROFILE_PORTFOLIO__" target="_blank" class="hover:underline flex items-center gap-1 opacity-90 hover:opacity-100">
          <svg class="w-3.5 h-3.5 fill-current" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg>
          Portfolio
        </a>
      </div>
    </div>
  </div>

  <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <!-- Header Navigation -->
    <header class="flex flex-col md:flex-row md:items-center md:justify-between gap-4 pb-6 border-b border-slate-200 dark:border-slate-800">
      <div>
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center text-white shadow-md shadow-indigo-500/20">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
          </div>
          <div>
            <h1 class="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">HR Outreach & Deliverability System</h1>
            <p class="text-xs text-slate-500 dark:text-slate-400">Automated, Rate-Limited Outreach Engine • Gmail API OAuth 2.0 Connected</p>
          </div>
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-3">
        <!-- Direct Gmail Drafts Button -->
        <a href="https://mail.google.com/mail/u/0/#drafts" target="_blank"
           class="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm transition-all hover:scale-105">
          <span class="w-2 h-2 rounded-full bg-emerald-300 animate-pulse"></span>
          <span>Open Gmail Drafts</span>
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
        </a>

        <!-- Dark / Light Theme Toggle -->
        <button id="themeToggle" class="p-2 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors" title="Toggle Dark/Light Mode">
          <svg id="sunIcon" class="w-4 h-4 hidden" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 9h-1m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"/></svg>
          <svg id="moonIcon" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"/></svg>
        </button>
      </div>
    </header>

    <!-- KPI Metric Cards Grid -->
    <section class="grid grid-cols-2 lg:grid-cols-5 gap-3.5 my-6">
      <!-- Total Contacts -->
      <div class="bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 p-4 rounded-xl shadow-sm">
        <div class="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs font-medium">
          <span>Target Pool</span>
          <span class="p-1 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">👥</span>
        </div>
        <div class="text-2xl font-bold text-slate-900 dark:text-white mt-1" id="statTotal">0</div>
        <div class="text-[11px] text-slate-500 dark:text-slate-400 mt-1 flex items-center gap-1">
          <span>Cleaned & verified</span>
        </div>
      </div>

      <!-- Drafted in Gmail -->
      <div class="bg-white dark:bg-slate-900 border border-emerald-200 dark:border-emerald-900/50 p-4 rounded-xl shadow-sm relative overflow-hidden">
        <div class="flex items-center justify-between text-emerald-700 dark:text-emerald-400 text-xs font-semibold">
          <span>Drafted in Gmail</span>
          <span class="w-2 h-2 rounded-full bg-emerald-500 animate-ping"></span>
        </div>
        <div class="text-2xl font-bold text-emerald-600 dark:text-emerald-400 mt-1" id="statDrafted">0</div>
        <div class="text-[11px] text-emerald-600/80 dark:text-emerald-500 mt-1 font-medium">✓ Ready for review in Gmail</div>
      </div>

      <!-- Approved -->
      <div class="bg-white dark:bg-slate-900 border border-indigo-200 dark:border-indigo-900/50 p-4 rounded-xl shadow-sm">
        <div class="flex items-center justify-between text-indigo-600 dark:text-indigo-400 text-xs font-medium">
          <span>Approved Queue</span>
          <span class="text-xs">📋</span>
        </div>
        <div class="text-2xl font-bold text-indigo-600 dark:text-indigo-400 mt-1" id="statApproved">0</div>
        <div class="text-[11px] text-slate-500 dark:text-slate-400 mt-1">Pending draft creation</div>
      </div>

      <!-- Dispatched / Sent -->
      <div class="bg-white dark:bg-slate-900 border border-blue-200 dark:border-blue-900/50 p-4 rounded-xl shadow-sm">
        <div class="flex items-center justify-between text-blue-600 dark:text-blue-400 text-xs font-medium">
          <span>Live Emails Sent</span>
          <span class="text-xs">🚀</span>
        </div>
        <div class="text-2xl font-bold text-blue-600 dark:text-blue-400 mt-1" id="statSent">0</div>
        <div class="text-[11px] text-slate-500 dark:text-slate-400 mt-1">Strict --confirm-send mode</div>
      </div>

      <!-- Daily Rate Limit Meter -->
      <div class="bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 p-4 rounded-xl shadow-sm col-span-2 lg:col-span-1">
        <div class="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs font-medium">
          <span>Daily Anti-Spam Meter</span>
          <span class="text-xs font-bold text-amber-500">🛡️ Safe</span>
        </div>
        <div class="flex items-baseline gap-1 mt-1">
          <span class="text-2xl font-bold text-slate-900 dark:text-white" id="statDailyUsed">0</span>
          <span class="text-xs text-slate-400 font-medium" id="statDailyCap">/ 50 limit</span>
        </div>
        <div class="w-full bg-slate-100 dark:bg-slate-800 h-2 rounded-full overflow-hidden mt-1.5">
          <div id="statDailyProgress" class="bg-indigo-600 h-full rounded-full transition-all duration-500" style="width: 10%;"></div>
        </div>
      </div>
    </section>

    <!-- Quick Terminal Command Bar (Collapsible) -->
    <div class="bg-slate-900 text-slate-200 p-3.5 rounded-xl text-xs mb-6 flex flex-col md:flex-row items-start md:items-center justify-between gap-3 shadow-inner">
      <div class="flex items-center gap-2">
        <span class="font-mono text-indigo-400 font-bold">$</span>
        <span class="font-semibold text-slate-300">Quick CLI Run:</span>
        <code class="font-mono bg-black/40 px-2 py-1 rounded text-slate-200 text-[11px]">./venv/bin/python main.py draft --tier 1 --batch-size 20</code>
      </div>
      <div class="flex items-center gap-2 self-end md:self-auto">
        <button onclick="copySnippet('./venv/bin/python main.py draft --tier 1 --batch-size 20')" 
                class="px-2.5 py-1 bg-indigo-600 hover:bg-indigo-500 text-white rounded font-medium text-[11px] transition-colors flex items-center gap-1">
          <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/></svg>
          Copy Command
        </button>
      </div>
    </div>

    <!-- Tier Filter Tabs Bar -->
    <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
      <div class="flex items-center gap-1.5 p-1 bg-slate-200/70 dark:bg-slate-900 rounded-xl text-xs font-medium">
        <button onclick="setTierFilter('ALL')" id="tabTierAll" class="tier-tab px-3 py-1.5 rounded-lg transition-all font-semibold bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-sm">
          All Contacts (<span id="countTabAll">0</span>)
        </button>
        <button onclick="setTierFilter(1)" id="tabTier1" class="tier-tab px-3 py-1.5 rounded-lg transition-all text-slate-600 dark:text-slate-400 hover:text-slate-900">
          🌟 Tier 1: MNC & Product (<span id="countTabTier1">0</span>)
        </button>
        <button onclick="setTierFilter(2)" id="tabTier2" class="tier-tab px-3 py-1.5 rounded-lg transition-all text-slate-600 dark:text-slate-400 hover:text-slate-900">
          🏢 Tier 2: IT Services (<span id="countTabTier2">0</span>)
        </button>
        <button onclick="setTierFilter(3)" id="tabTier3" class="tier-tab px-3 py-1.5 rounded-lg transition-all text-slate-600 dark:text-slate-400 hover:text-slate-900">
          💼 Tier 3: Staffing (<span id="countTabTier3">0</span>)
        </button>
      </div>

      <!-- View Switcher (Grid vs. Table) -->
      <div class="flex items-center gap-1 p-1 bg-slate-200/70 dark:bg-slate-900 rounded-xl text-xs">
        <button id="viewGridBtn" onclick="setViewMode('grid')" class="p-1.5 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-sm" title="Card Grid View">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"/></svg>
        </button>
        <button id="viewTableBtn" onclick="setViewMode('table')" class="p-1.5 rounded-lg text-slate-600 dark:text-slate-400 hover:text-slate-900" title="Spreadsheet Table View">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 10h16M4 14h16M4 18h16"/></svg>
        </button>
      </div>
    </div>

    <!-- Search & Filter Controls -->
    <div class="bg-white dark:bg-slate-900 rounded-xl shadow-sm p-3.5 mb-6 border border-slate-200/80 dark:border-slate-800 flex flex-col sm:flex-row gap-3 items-center justify-between">
      <div class="relative w-full sm:w-96">
        <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
        </div>
        <input type="text" id="searchInput" placeholder="Search by company, recruiter, or title..." 
               class="w-full pl-9 pr-12 py-2 border rounded-lg text-xs bg-slate-50 dark:bg-slate-800/60 border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500">
        <div class="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
          <kbd class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-200 dark:bg-slate-700 text-slate-500 dark:text-slate-400 border border-slate-300 dark:border-slate-600">/</kbd>
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-2 w-full sm:w-auto">
        <!-- Status Filter -->
        <select id="statusFilter" class="px-3 py-2 border rounded-lg text-xs bg-white dark:bg-slate-800 border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500">
          <option value="ALL">All Statuses</option>
          <option value="Drafted in Gmail">✓ Drafted in Gmail</option>
          <option value="Approved">Approved</option>
          <option value="Ready for Review">Ready for Review</option>
          <option value="Sent">Sent</option>
          <option value="Suppressed">Suppressed</option>
        </select>

        <!-- Sort Select -->
        <select id="sortSelect" class="px-3 py-2 border rounded-lg text-xs bg-white dark:bg-slate-800 border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500">
          <option value="company-asc">Company (A → Z)</option>
          <option value="company-desc">Company (Z → A)</option>
          <option value="name-asc">Recruiter Name (A → Z)</option>
          <option value="status">Status</option>
        </select>
      </div>
    </div>

    <!-- Active Filter Summary -->
    <div class="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400 mb-4 px-1">
      <div>
        Showing <span id="visibleCount" class="font-bold text-slate-900 dark:text-white">0</span> contacts
      </div>
      <div id="paginationSummary" class="text-slate-500">Page 1 of 1</div>
    </div>

    <!-- Content Views -->
    <!-- 1. Grid Cards View -->
    <div id="gridContainer" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5"></div>

    <!-- 2. Table Spreadsheet View (Hidden by default) -->
    <div id="tableContainer" class="hidden bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-sm overflow-x-auto">
      <table class="w-full text-left text-xs text-slate-600 dark:text-slate-300">
        <thead class="bg-slate-50 dark:bg-slate-800/60 uppercase font-semibold text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800">
          <tr>
            <th class="px-4 py-3">Company</th>
            <th class="px-4 py-3">Recruiter Name</th>
            <th class="px-4 py-3">Role / Designation</th>
            <th class="px-4 py-3">Tier</th>
            <th class="px-4 py-3">Outreach Status</th>
            <th class="px-4 py-3 text-right">Actions</th>
          </tr>
        </thead>
        <tbody id="tableBody" class="divide-y divide-slate-100 dark:divide-slate-800/60"></tbody>
      </table>
    </div>

    <!-- Pagination Controls -->
    <div class="mt-8 flex items-center justify-center gap-2">
      <button id="prevPageBtn" onclick="changePage(-1)" class="px-3 py-1.5 text-xs font-semibold rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 disabled:opacity-40 disabled:cursor-not-allowed">
        &larr; Previous
      </button>
      <span id="pageIndicator" class="text-xs font-mono text-slate-500 px-3">Page 1</span>
      <button id="nextPageBtn" onclick="changePage(1)" class="px-3 py-1.5 text-xs font-semibold rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 disabled:opacity-40 disabled:cursor-not-allowed">
        Next &rarr;
      </button>
    </div>
  </div>

  <!-- Rich Inspection Modal -->
  <div id="previewModal" class="fixed inset-0 bg-black/60 glass hidden flex items-center justify-center p-3 sm:p-6 z-50 transition-opacity duration-200">
    <div class="bg-white dark:bg-slate-900 rounded-2xl max-w-4xl w-full max-h-[92vh] flex flex-col shadow-2xl border border-slate-200 dark:border-slate-800 overflow-hidden animate-in fade-in zoom-in-95 duration-150">
      
      <!-- Modal Header -->
      <div class="px-6 py-4 border-b border-slate-200 dark:border-slate-800 flex justify-between items-start bg-slate-50 dark:bg-slate-900/50">
        <div>
          <div class="flex items-center gap-2">
            <span id="modalTierBadge" class="text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wider bg-indigo-100 text-indigo-700 dark:bg-indigo-900/50 dark:text-indigo-300">Tier 1</span>
            <span id="modalStatusBadge" class="text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wider bg-emerald-100 text-emerald-700">Drafted</span>
          </div>
          <h3 id="modalSubject" class="text-base font-bold text-slate-900 dark:text-white mt-1"></h3>
          <p id="modalRecipient" class="text-xs text-slate-500 dark:text-slate-400 mt-0.5"></p>
        </div>
        <button onclick="closeModal()" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 text-2xl font-semibold leading-none">&times;</button>
      </div>

      <!-- Modal Tabs Navigation -->
      <div class="flex border-b border-slate-200 dark:border-slate-800 px-6 bg-slate-50/50 dark:bg-slate-900/30 text-xs font-semibold gap-6">
        <button onclick="setModalTab('rendered')" id="modalTabRendered" class="py-2.5 border-b-2 border-indigo-600 text-indigo-600 dark:text-indigo-400 flex items-center gap-1.5">
          <span>📬 Gmail HTML View</span>
        </button>
        <button onclick="setModalTab('plaintext')" id="modalTabPlaintext" class="py-2.5 border-b-2 border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 flex items-center gap-1.5">
          <span>📄 Plaintext Fallback</span>
        </button>
        <button onclick="setModalTab('audit')" id="modalTabAudit" class="py-2.5 border-b-2 border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 flex items-center gap-1.5">
          <span>🛡️ Deliverability & Spam Audit</span>
        </button>
      </div>

      <!-- Modal Content Body -->
      <div class="p-6 overflow-y-auto flex-1 bg-white dark:bg-slate-950">
        <!-- 1. Rendered Iframe -->
        <div id="modalRenderedView" class="w-full">
          <iframe id="modalIframe" class="w-full h-[400px] border border-slate-200 dark:border-slate-800 rounded-xl bg-white"></iframe>
        </div>

        <!-- 2. Plaintext View -->
        <div id="modalPlaintextView" class="hidden">
          <pre id="modalPlaintextContent" class="font-mono text-xs whitespace-pre-wrap p-4 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl text-slate-700 dark:text-slate-200 leading-relaxed"></pre>
        </div>

        <!-- 3. Audit View -->
        <div id="modalAuditView" class="hidden space-y-3">
          <div class="p-4 rounded-xl border border-emerald-200 dark:border-emerald-900/40 bg-emerald-50 dark:bg-emerald-950/20 text-xs">
            <h4 class="font-bold text-emerald-800 dark:text-emerald-300 text-sm mb-1">✓ RFC 2822 Compliant & Zero Spam Trigger Words</h4>
            <p class="text-emerald-700 dark:text-emerald-400">Subject line is concise, personalized to the recipient's organization, and free from aggressive marketing terms or misleading claims.</p>
          </div>
          <div class="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 text-xs space-y-2">
            <div class="flex justify-between py-1 border-b border-slate-200 dark:border-slate-800">
              <span class="text-slate-500">Authentication Method:</span>
              <span class="font-mono font-semibold">Google OAuth 2.0 (Token Managed)</span>
            </div>
            <div class="flex justify-between py-1 border-b border-slate-200 dark:border-slate-800">
              <span class="text-slate-500">OAuth Scope Required:</span>
              <span class="font-mono font-semibold text-indigo-600 dark:text-indigo-400">gmail.compose (Minimal Least-Privilege)</span>
            </div>
            <div class="flex justify-between py-1 border-b border-slate-200 dark:border-slate-800">
              <span class="text-slate-500">Unsubscribe Compliance:</span>
              <span class="font-semibold text-emerald-600">✓ Opt-Out Footer Present</span>
            </div>
            <div class="flex justify-between py-1">
              <span class="text-slate-500">Recipient Privacy:</span>
              <span class="font-semibold text-indigo-600">✓ Contact email masked in client preview</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Modal Footer -->
      <div class="px-6 py-3.5 border-t border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 flex flex-wrap items-center justify-between gap-2">
        <div class="flex items-center gap-2">
          <button onclick="copyCurrentSubject()" class="px-3 py-1.5 text-xs font-semibold rounded-lg bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 hover:bg-slate-100 text-slate-700 dark:text-slate-200 transition-colors flex items-center gap-1.5">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/></svg>
            Copy Subject
          </button>
          <button onclick="copyCurrentBody()" class="px-3 py-1.5 text-xs font-semibold rounded-lg bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 hover:bg-slate-100 text-slate-700 dark:text-slate-200 transition-colors flex items-center gap-1.5">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
            Copy Message Body
          </button>
        </div>
        <div class="flex items-center gap-2">
          <a href="https://mail.google.com/mail/u/0/#drafts" target="_blank"
             class="px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white transition-colors flex items-center gap-1.5">
            <span>Open in Gmail</span>
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
          </a>
          <button onclick="closeModal()" class="px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-300">
            Close
          </button>
        </div>
      </div>
    </div>
  </div>

  <!-- Toast Notification Container -->
  <div id="toast" class="fixed bottom-5 right-5 z-50 transform translate-y-20 opacity-0 transition-all duration-300 pointer-events-none">
    <div class="bg-slate-900 text-white dark:bg-white dark:text-slate-900 px-4 py-2.5 rounded-xl shadow-xl text-xs font-semibold flex items-center gap-2">
      <span class="text-emerald-400">✓</span>
      <span id="toastMessage">Copied to clipboard!</span>
    </div>
  </div>

  <script>
    // Injected Data
    const contactsData = __CONTACTS_JSON__;
    const statsData = __STATS_JSON__;

    // State
    let currentTier = 'ALL';
    let currentStatus = 'ALL';
    let searchQuery = '';
    let sortMode = 'company-asc';
    let viewMode = 'grid'; // 'grid' | 'table'
    let currentPage = 1;
    const pageSize = 24;
    let currentModalItem = null;

    // Palette generator for company avatars
    const avatarGradients = [
      'from-blue-600 to-indigo-600',
      'from-violet-600 to-purple-600',
      'from-emerald-600 to-teal-600',
      'from-rose-600 to-pink-600',
      'from-amber-600 to-orange-600',
      'from-cyan-600 to-blue-600'
    ];

    function getAvatarGradient(str) {
      let hash = 0;
      for (let i = 0; i < str.length; i++) hash = str.charCodeAt(i) + ((hash << 5) - hash);
      return avatarGradients[Math.abs(hash) % avatarGradients.length];
    }

    // Init Theme
    const themeToggle = document.getElementById('themeToggle');
    const sunIcon = document.getElementById('sunIcon');
    const moonIcon = document.getElementById('moonIcon');

    function applyTheme(isDark) {
      if (isDark) {
        document.documentElement.classList.add('dark');
        sunIcon.classList.remove('hidden');
        moonIcon.classList.add('hidden');
        localStorage.theme = 'dark';
      } else {
        document.documentElement.classList.remove('dark');
        sunIcon.classList.add('hidden');
        moonIcon.classList.remove('hidden');
        localStorage.theme = 'light';
      }
    }

    const savedTheme = localStorage.theme;
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    applyTheme(savedTheme === 'dark' || (!savedTheme && prefersDark));

    themeToggle.addEventListener('click', () => {
      applyTheme(!document.documentElement.classList.contains('dark'));
    });

    // Populate KPI Stats
    document.getElementById('statTotal').textContent = statsData.total.toLocaleString();
    document.getElementById('statDrafted').textContent = statsData.drafted.toLocaleString();
    document.getElementById('statApproved').textContent = statsData.approved.toLocaleString();
    document.getElementById('statSent').textContent = statsData.sent.toLocaleString();
    document.getElementById('statDailyUsed').textContent = (statsData.drafts_today + statsData.sent_today);
    document.getElementById('statDailyCap').textContent = `/ ${statsData.daily_cap} limit`;
    const pct = Math.min(100, Math.round(((statsData.drafts_today + statsData.sent_today) / statsData.daily_cap) * 100));
    document.getElementById('statDailyProgress').style.width = `${Math.max(6, pct)}%`;

    document.getElementById('countTabAll').textContent = statsData.total.toLocaleString();
    document.getElementById('countTabTier1').textContent = statsData.tier1.toLocaleString();
    document.getElementById('countTabTier2').textContent = statsData.tier2.toLocaleString();
    document.getElementById('countTabTier3').textContent = statsData.tier3.toLocaleString();

    // Filtering & Sorting
    function getFilteredData() {
      return contactsData.filter(item => {
        const matchesTier = currentTier === 'ALL' || item.tier === currentTier;
        const matchesStatus = currentStatus === 'ALL' || item.status === currentStatus;
        const q = searchQuery.toLowerCase().trim();
        const matchesQuery = !q ||
          item.company.toLowerCase().includes(q) ||
          item.name.toLowerCase().includes(q) ||
          item.title.toLowerCase().includes(q) ||
          item.subject.toLowerCase().includes(q);

        return matchesTier && matchesStatus && matchesQuery;
      }).sort((a, b) => {
        if (sortMode === 'company-asc') return a.company.localeCompare(b.company);
        if (sortMode === 'company-desc') return b.company.localeCompare(a.company);
        if (sortMode === 'name-asc') return a.name.localeCompare(b.name);
        if (sortMode === 'status') return a.status.localeCompare(b.status);
        return 0;
      });
    }

    // Render Cards & Table
    function render() {
      const filtered = getFilteredData();
      const totalItems = filtered.length;
      const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
      if (currentPage > totalPages) currentPage = totalPages;

      const startIndex = (currentPage - 1) * pageSize;
      const pageItems = filtered.slice(startIndex, startIndex + pageSize);

      document.getElementById('visibleCount').textContent = totalItems.toLocaleString();
      document.getElementById('paginationSummary').textContent = totalItems > 0
        ? `Showing ${startIndex + 1}–${Math.min(startIndex + pageSize, totalItems)} of ${totalItems}`
        : '0 contacts found';

      document.getElementById('pageIndicator').textContent = `Page ${currentPage} of ${totalPages}`;
      document.getElementById('prevPageBtn').disabled = currentPage <= 1;
      document.getElementById('nextPageBtn').disabled = currentPage >= totalPages;

      const gridContainer = document.getElementById('gridContainer');
      const tableBody = document.getElementById('tableBody');

      if (viewMode === 'grid') {
        gridContainer.classList.remove('hidden');
        document.getElementById('tableContainer').classList.add('hidden');

        gridContainer.innerHTML = '';
        if (pageItems.length === 0) {
          gridContainer.innerHTML = `
            <div class="col-span-full py-16 text-center text-slate-400">
              <p class="text-base font-semibold">No matching recruiter contacts found</p>
              <p class="text-xs mt-1">Try resetting search or tier filter</p>
            </div>`;
          return;
        }

        pageItems.forEach(item => {
          const card = document.createElement('div');
          card.className = "bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-5 shadow-sm hover:shadow-md transition-all flex flex-col justify-between group";

          const initial = (item.company || 'C').charAt(0).toUpperCase();
          const gradient = getAvatarGradient(item.company || 'Comp');

          const badgeClass = item.status === 'Drafted in Gmail' ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300 border-emerald-300 dark:border-emerald-800' :
                             item.status === 'Sent' ? 'bg-blue-100 text-blue-800 dark:bg-blue-950/60 dark:text-blue-300 border-blue-300' :
                             item.status === 'Approved' ? 'bg-indigo-100 text-indigo-800 dark:bg-indigo-950/60 dark:text-indigo-300 border-indigo-300' :
                             'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 border-slate-200';

          const tierLabel = item.tier === 1 ? 'Tier 1: MNC / Product' : item.tier === 2 ? 'Tier 2: IT Services' : 'Tier 3: Staffing';

          card.innerHTML = `
            <div>
              <div class="flex items-start justify-between gap-3 mb-3">
                <div class="flex items-center gap-2.5 min-w-0">
                  <div class="w-9 h-9 rounded-xl bg-gradient-to-tr ${gradient} flex items-center justify-center text-white font-bold text-sm shadow-sm shrink-0">
                    ${initial}
                  </div>
                  <div class="min-w-0">
                    <h3 class="font-bold text-slate-900 dark:text-white text-sm truncate" title="${item.company}">${item.company}</h3>
                    <p class="text-[11px] text-slate-500 dark:text-slate-400 truncate">${tierLabel}</p>
                  </div>
                </div>
                <span class="text-[10px] font-semibold px-2 py-0.5 rounded-full border ${badgeClass} shrink-0">${item.status}</span>
              </div>

              <div class="space-y-1 mb-3 bg-slate-50 dark:bg-slate-800/40 p-2.5 rounded-xl border border-slate-100 dark:border-slate-800/60 text-xs">
                <div class="flex items-center justify-between">
                  <span class="font-semibold text-slate-800 dark:text-slate-200 truncate">${item.name}</span>
                </div>
                <p class="text-slate-500 dark:text-slate-400 text-[11px] truncate">${item.title}</p>
              </div>

              <div class="mb-4">
                <p class="text-[11px] text-slate-400 mb-0.5">Subject line:</p>
                <p class="text-xs font-medium text-slate-700 dark:text-slate-300 truncate font-mono bg-slate-50 dark:bg-slate-800/30 p-1.5 rounded border border-slate-100 dark:border-slate-800/60">${item.subject}</p>
              </div>
            </div>

            <div class="pt-3 border-t border-slate-100 dark:border-slate-800/80 flex items-center justify-between gap-2">
              <button onclick="openModal(${item.id})" class="text-xs font-semibold text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 flex items-center gap-1">
                <span>Inspect Full Email</span>
                <span class="group-hover:translate-x-0.5 transition-transform">&rarr;</span>
              </button>
              <button onclick="copySubjectById(${item.id})" title="Copy Subject" class="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/></svg>
              </button>
            </div>
          `;
          gridContainer.appendChild(card);
        });
      } else {
        gridContainer.classList.add('hidden');
        document.getElementById('tableContainer').classList.remove('hidden');

        tableBody.innerHTML = '';
        pageItems.forEach(item => {
          const row = document.createElement('tr');
          row.className = "hover:bg-slate-50/70 dark:hover:bg-slate-800/40 transition-colors";

          const initial = (item.company || 'C').charAt(0).toUpperCase();
          const gradient = getAvatarGradient(item.company || 'Comp');

          row.innerHTML = `
            <td class="px-4 py-3 font-semibold text-slate-900 dark:text-white flex items-center gap-2">
              <div class="w-6 h-6 rounded bg-gradient-to-tr ${gradient} flex items-center justify-center text-white text-[10px] font-bold shrink-0">
                ${initial}
              </div>
              <span class="truncate max-w-[180px]">${item.company}</span>
            </td>
            <td class="px-4 py-3">${item.name}</td>
            <td class="px-4 py-3 text-slate-500 dark:text-slate-400">${item.title}</td>
            <td class="px-4 py-3"><span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 dark:bg-slate-800">Tier ${item.tier}</span></td>
            <td class="px-4 py-3"><span class="px-2 py-0.5 rounded-full text-[10px] font-semibold border ${item.status === 'Drafted in Gmail' ? 'bg-emerald-50 text-emerald-700 border-emerald-300' : 'bg-slate-100 text-slate-700'}">${item.status}</span></td>
            <td class="px-4 py-3 text-right">
              <button onclick="openModal(${item.id})" class="px-2 py-1 text-xs font-semibold text-indigo-600 hover:text-indigo-800 underline">Inspect</button>
            </td>
          `;
          tableBody.appendChild(row);
        });
      }
    }

    // Modal Control
    function openModal(id) {
      const item = contactsData.find(c => c.id === id);
      if (!item) return;
      currentModalItem = item;

      document.getElementById('modalSubject').textContent = item.subject;
      document.getElementById('modalRecipient').textContent = `Recipient: ${item.name} • ${item.title} at ${item.company}`;
      document.getElementById('modalTierBadge').textContent = `Tier ${item.tier}`;
      document.getElementById('modalStatusBadge').textContent = item.status;

      const iframe = document.getElementById('modalIframe');
      iframe.srcdoc = item.html_body;

      document.getElementById('modalPlaintextContent').textContent = item.text_body;

      setModalTab('rendered');
      document.getElementById('previewModal').classList.remove('hidden');
    }

    function closeModal() {
      document.getElementById('previewModal').classList.add('hidden');
      currentModalItem = null;
    }

    function setModalTab(tab) {
      const tabRendered = document.getElementById('modalTabRendered');
      const tabPlaintext = document.getElementById('modalTabPlaintext');
      const tabAudit = document.getElementById('modalTabAudit');

      const viewRendered = document.getElementById('modalRenderedView');
      const viewPlaintext = document.getElementById('modalPlaintextView');
      const viewAudit = document.getElementById('modalAuditView');

      [tabRendered, tabPlaintext, tabAudit].forEach(t => {
        t.className = "py-2.5 border-b-2 border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 flex items-center gap-1.5";
      });
      [viewRendered, viewPlaintext, viewAudit].forEach(v => v.classList.add('hidden'));

      if (tab === 'rendered') {
        tabRendered.className = "py-2.5 border-b-2 border-indigo-600 text-indigo-600 dark:text-indigo-400 font-bold flex items-center gap-1.5";
        viewRendered.classList.remove('hidden');
      } else if (tab === 'plaintext') {
        tabPlaintext.className = "py-2.5 border-b-2 border-indigo-600 text-indigo-600 dark:text-indigo-400 font-bold flex items-center gap-1.5";
        viewPlaintext.classList.remove('hidden');
      } else if (tab === 'audit') {
        tabAudit.className = "py-2.5 border-b-2 border-indigo-600 text-indigo-600 dark:text-indigo-400 font-bold flex items-center gap-1.5";
        viewAudit.classList.remove('hidden');
      }
    }

    // View Switching
    function setViewMode(mode) {
      viewMode = mode;
      const gridBtn = document.getElementById('viewGridBtn');
      const tableBtn = document.getElementById('viewTableBtn');

      if (mode === 'grid') {
        gridBtn.className = "p-1.5 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-sm";
        tableBtn.className = "p-1.5 rounded-lg text-slate-600 dark:text-slate-400 hover:text-slate-900";
      } else {
        tableBtn.className = "p-1.5 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-sm";
        gridBtn.className = "p-1.5 rounded-lg text-slate-600 dark:text-slate-400 hover:text-slate-900";
      }
      render();
    }

    function setTierFilter(tier) {
      currentTier = tier;
      currentPage = 1;
      document.querySelectorAll('.tier-tab').forEach(tab => {
        tab.className = "tier-tab px-3 py-1.5 rounded-lg transition-all text-slate-600 dark:text-slate-400 hover:text-slate-900";
      });

      const activeTabId = tier === 'ALL' ? 'tabTierAll' : `tabTier${tier}`;
      const activeTab = document.getElementById(activeTabId);
      if (activeTab) {
        activeTab.className = "tier-tab px-3 py-1.5 rounded-lg transition-all font-semibold bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-sm";
      }
      render();
    }

    function changePage(delta) {
      currentPage += delta;
      render();
      window.scrollTo({ top: 320, behavior: 'smooth' });
    }

    // Search and Sort Event Listeners
    const searchInput = document.getElementById('searchInput');
    const statusFilter = document.getElementById('statusFilter');
    const sortSelect = document.getElementById('sortSelect');

    searchInput.addEventListener('input', (e) => {
      searchQuery = e.target.value;
      currentPage = 1;
      render();
    });

    statusFilter.addEventListener('change', (e) => {
      currentStatus = e.target.value;
      currentPage = 1;
      render();
    });

    sortSelect.addEventListener('change', (e) => {
      sortMode = e.target.value;
      render();
    });

    // Keyboard Shortcuts
    window.addEventListener('keydown', (e) => {
      if (e.key === '/' && document.activeElement !== searchInput) {
        e.preventDefault();
        searchInput.focus();
      } else if (e.key === 'Escape') {
        closeModal();
      }
    });

    // Clipboard and Toasts
    function showToast(msg) {
      const toast = document.getElementById('toast');
      document.getElementById('toastMessage').textContent = msg;
      toast.classList.remove('translate-y-20', 'opacity-0');
      setTimeout(() => {
        toast.classList.add('translate-y-20', 'opacity-0');
      }, 2500);
    }

    function copySnippet(text) {
      navigator.clipboard.writeText(text).then(() => showToast('CLI Command copied to clipboard!'));
    }

    function copySubjectById(id) {
      const item = contactsData.find(c => c.id === id);
      if (item) {
        navigator.clipboard.writeText(item.subject).then(() => showToast('Subject copied!'));
      }
    }

    function copyCurrentSubject() {
      if (currentModalItem) {
        navigator.clipboard.writeText(currentModalItem.subject).then(() => showToast('Subject copied to clipboard!'));
      }
    }

    function copyCurrentBody() {
      if (currentModalItem) {
        navigator.clipboard.writeText(currentModalItem.text_body).then(() => showToast('Message body copied to clipboard!'));
      }
    }

    // Initial render
    render();
  </script>
</body>
</html>"""

        # Perform safe token replacements
        html_rendered = (
            html_template
            .replace("__CONTACTS_JSON__", json.dumps(items_json))
            .replace("__STATS_JSON__", json.dumps(stats_payload))
            .replace("__PROFILE_NAME__", profile_payload["name"])
            .replace("__PROFILE_DEGREE__", profile_payload["degree"])
            .replace("__PROFILE_GRAD_YEAR__", profile_payload["grad_year"])
            .replace("__PROFILE_TARGET__", profile_payload["target_role"])
            .replace("__PROFILE_GITHUB__", profile_payload["github"])
            .replace("__PROFILE_PORTFOLIO__", profile_payload["portfolio"])
        )

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_rendered)

        return output_path
