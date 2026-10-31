"""
Interactive Email Preview, Approval Workflow, and HTML Dashboard Generator
"""
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt

console = Console()

class PreviewApprovalSystem:
    """Manages terminal-based review and generates standalone HTML preview dashboards."""

    def __init__(self, template_engine: Any, tracker: Any):
        self.template_engine = template_engine
        self.tracker = tracker

    def render_cli_preview(self, contact: Dict[str, Any], rendered: Dict[str, Any], index: int, total: int):
        """Display formatted card in terminal."""
        meta_table = Table(show_header=False, box=None, padding=(0, 1))
        meta_table.add_row("[bold cyan]Recipient:[/]", f"{contact.get('cleaned_name', 'N/A')} <{contact.get('email')}>")
        meta_table.add_row("[bold cyan]Company:[/]", f"{contact.get('cleaned_company', 'N/A')}")
        meta_table.add_row("[bold cyan]Title/Role:[/]", f"{contact.get('job_title', 'N/A')}")
        meta_table.add_row("[bold cyan]Template:[/]", f"{rendered.get('template_name')}")
        meta_table.add_row("[bold cyan]Subject:[/]", f"[bold yellow]{rendered.get('subject')}[/]")

        warnings = rendered.get("spam_warnings", [])
        if warnings:
            meta_table.add_row("[bold red]Warnings:[/]", f"[red]{'; '.join(warnings)}[/]")

        console.print("\n" + "=" * 80)
        console.print(Panel(
            meta_table,
            title=f"[bold green]Email Preview ({index}/{total})[/]",
            subtitle="[dim]Check details before approval[/dim]"
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
            
            # Skip if already contacted or suppressed
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
                "[bold yellow]Action[/]",
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
                console.print(f"[bold green]✓ Approved for outreach: {email}[/]")
            elif choice == "r":
                self.tracker.upsert_contact_status(
                    email=email,
                    name=contact.get("cleaned_name", ""),
                    company=contact.get("cleaned_company", ""),
                    status="REJECTED",
                    tier=int(contact.get("tier", 1))
                )
                console.print(f"[bold red]✗ Rejected / Skipped: {email}[/]")
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
        counts = {"total": len(contacts), "drafted": 0, "approved": 0, "sent": 0, "review": 0}

        for c in contacts:
            email = _clean_val(c.get("email"))
            rendered = self.template_engine.render(c)
            is_supp = self.tracker.is_suppressed(email)
            
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

            masked_email = ""
            if email and "@" in email:
                p = email.split("@")
                masked_email = f"{p[0][:1]}***@{p[1]}"

            items_json.append({
                "email": masked_email,
                "name": _clean_val(c.get("cleaned_name"), "Hiring Team"),
                "company": _clean_val(c.get("cleaned_company"), "N/A"),
                "title": _clean_val(c.get("job_title"), "Recruiter"),
                "status": status,
                "tier": c.get("tier", 1),
                "draft_id": draft_id,
                "template": rendered.get("template_name"),
                "subject": rendered.get("subject"),
                "text_body": rendered.get("text_body"),
                "html_body": rendered.get("html_body")
            })

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>HR Outreach Preview & Tracking Dashboard</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    .modal-backdrop {{ background-color: rgba(0, 0, 0, 0.5); }}
  </style>
</head>
<body class="bg-slate-50 text-slate-800 min-h-screen">
  <div class="max-w-7xl mx-auto px-4 py-8">
    <!-- Header -->
    <header class="mb-8 flex flex-col md:flex-row md:items-center md:justify-between border-b pb-6">
      <div>
        <h1 class="text-3xl font-bold tracking-tight text-slate-900">Outreach Email Preview & Tracking</h1>
        <p class="text-sm text-slate-500 mt-1">Review personalized emails, inspect subjects, and audit anti-spam compliance</p>
      </div>
      <div class="mt-4 md:mt-0 flex flex-wrap gap-2 items-center">
        <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-slate-200 text-slate-800">
          Total: <strong class="ml-1">{len(items_json)}</strong>
        </span>
        <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-300">
          ✓ Drafted in Gmail: <strong class="ml-1">{counts["drafted"]}</strong>
        </span>
        <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800">
          Approved: <strong class="ml-1">{counts["approved"]}</strong>
        </span>
        <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
          Sent: <strong class="ml-1">{counts["sent"]}</strong>
        </span>
      </div>
    </header>

    <!-- Filter & Search Controls -->
    <div class="bg-white rounded-xl shadow-sm p-4 mb-6 border border-slate-200 flex flex-col sm:flex-row gap-4 justify-between items-center">
      <div class="w-full sm:w-96">
        <input type="text" id="searchInput" placeholder="Search by name, company, or email..." 
               class="w-full px-4 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 border-slate-300">
      </div>
      <div class="flex gap-2 w-full sm:w-auto">
        <select id="statusFilter" class="px-3 py-2 border rounded-lg text-sm bg-white border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500">
          <option value="ALL">All Statuses</option>
          <option value="Drafted in Gmail">✓ Drafted in Gmail</option>
          <option value="Approved">Approved</option>
          <option value="Ready for Review">Ready for Review</option>
          <option value="Sent">Sent</option>
          <option value="Suppressed">Suppressed</option>
        </select>
      </div>
    </div>

    <!-- Contact Cards Grid -->
    <div id="cardsContainer" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"></div>
  </div>

  <!-- Preview Modal -->
  <div id="previewModal" class="fixed inset-0 modal-backdrop hidden flex items-center justify-center p-4 z-50">
    <div class="bg-white rounded-2xl max-w-3xl w-full max-h-[90vh] flex flex-col shadow-2xl overflow-hidden">
      <div class="px-6 py-4 border-b flex justify-between items-center bg-slate-50">
        <div>
          <h3 id="modalSubject" class="text-base font-bold text-slate-900"></h3>
          <p id="modalRecipient" class="text-xs text-slate-500 mt-0.5"></p>
        </div>
        <button onclick="closeModal()" class="text-slate-400 hover:text-slate-600 text-2xl font-semibold">&times;</button>
      </div>
      <div class="p-6 overflow-y-auto flex-1 bg-white">
        <iframe id="modalIframe" class="w-full h-96 border-0 rounded"></iframe>
      </div>
      <div class="px-6 py-3 border-t bg-slate-50 flex justify-end">
        <button onclick="closeModal()" class="px-4 py-2 text-sm font-medium bg-slate-200 hover:bg-slate-300 text-slate-700 rounded-lg">Close</button>
      </div>
    </div>
  </div>

  <script>
    const data = {json.dumps(items_json)};
    const container = document.getElementById('cardsContainer');
    const searchInput = document.getElementById('searchInput');
    const statusFilter = document.getElementById('statusFilter');

    function renderCards(items) {{
      container.innerHTML = '';
      if (items.length === 0) {{
        container.innerHTML = '<div class="col-span-full py-12 text-center text-slate-400">No matching contacts found.</div>';
        return;
      }}
      items.forEach((item, idx) => {{
        const card = document.createElement('div');
        card.className = "bg-white border border-slate-200 rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow flex flex-col justify-between";
        
        const badgeColor = item.status === 'Drafted in Gmail' ? 'bg-emerald-100 text-emerald-800 border-emerald-300 font-semibold' :
                           item.status === 'Sent' ? 'bg-blue-100 text-blue-800 border-blue-300 font-semibold' :
                           item.status === 'Approved' ? 'bg-indigo-50 text-indigo-700 border-indigo-200' :
                           item.status === 'Suppressed' ? 'bg-red-50 text-red-700 border-red-200' : 'bg-slate-100 text-slate-700 border-slate-200';

        card.innerHTML = `
          <div>
            <div class="flex justify-between items-start mb-3">
              <span class="text-xs px-2.5 py-0.5 rounded-full border ${{badgeColor}}">${{item.status}}</span>
              <span class="text-xs text-slate-400 truncate max-w-[150px]">${{item.template}}</span>
            </div>
            <h3 class="font-bold text-slate-900 text-base mb-1 truncate">${{item.name}}</h3>
            <p class="text-sm font-medium text-indigo-600 mb-0.5 truncate">${{item.company}}</p>
            <p class="text-xs text-slate-500 mb-3 truncate flex items-center">
              <span class="text-slate-400 mr-1.5">Role:</span> ${{item.title}}
            </p>
            <div class="bg-slate-50 p-2.5 rounded-lg border border-slate-100 text-xs mb-4">
              <span class="font-semibold text-slate-700">Subject:</span>
              <p class="text-slate-600 truncate mt-0.5">${{item.subject}}</p>
            </div>
          </div>
          <div class="pt-2 border-t border-slate-100 flex justify-between items-center">
            <button onclick="openModal(${{idx}})" class="text-xs font-medium text-indigo-600 hover:text-indigo-800 hover:underline">
              Inspect Full Email &rarr;
            </button>
          </div>
        `;
        container.appendChild(card);
      }});
    }}

    function filterData() {{
      const q = searchInput.value.toLowerCase();
      const status = statusFilter.value;
      const filtered = data.filter(item => {{
        const matchesQuery = item.name.toLowerCase().includes(q) ||
                             item.company.toLowerCase().includes(q) ||
                             item.title.toLowerCase().includes(q);
        const matchesStatus = status === 'ALL' || item.status === status;
        return matchesQuery && matchesStatus;
      }});
      renderCards(filtered);
    }}

    searchInput.addEventListener('input', filterData);
    statusFilter.addEventListener('change', filterData);

    function openModal(idx) {{
      const item = data[idx];
      document.getElementById('modalSubject').textContent = item.subject;
      document.getElementById('modalRecipient').textContent = `To: ${{item.name}} at ${{item.company}} (${{item.title}})`;
      const iframe = document.getElementById('modalIframe');
      iframe.srcdoc = item.html_body;
      document.getElementById('previewModal').classList.remove('hidden');
    }}

    function closeModal() {{
      document.getElementById('previewModal').classList.add('hidden');
    }}

    // Initial render
    renderCards(data);
  </script>
</body>
</html>
"""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        return output_path
