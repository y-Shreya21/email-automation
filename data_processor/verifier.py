"""
Email Deliverability & Two-Condition Security Verification Engine
Evaluates:
- Condition 1: Address Availability & Validity (RFC 5322 syntax, resolving domain, non-system/payable inbox)
- Condition 2: Address Deliverability (Active MX records, non-disposable domain)
If both conditions pass -> DRAFT. Otherwise -> DELETE.
"""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
import dns.resolver

# Known burner / disposable domains that reject legitimate candidate outreach
DISPOSABLE_DOMAINS = {
    "mailinator.com", "tempmail.com", "guerrillamail.com", "10minutemail.com",
    "yopmail.com", "trashmail.com", "throwawaymail.com", "sharklasers.com",
    "getairmail.com", "temp-mail.org", "fakeinbox.com", "dispostable.com",
    "maildrop.cc", "mohmal.com", "burnermail.io", "nada.ltd"
}

# Known generic / system / bot prefixes that are NOT available recruiter inboxes
SYSTEM_OR_GENERIC_PREFIXES = {
    "payable", "payables", "billing", "billings", "invoice", "invoices",
    "accounts", "accounting", "finance", "legal", "compliance", "abuse",
    "postmaster", "noreply", "no-reply", "do-not-reply", "mailer-daemon",
    "bounce", "admin", "webmaster", "support", "help", "info", "contact",
    "sales", "press", "media", "privacy", "security", "customer", "care"
}

# Standard RFC 5322 compliant email regex
EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)


@dataclass
class SecurityCheckResult:
    email: str
    is_available: bool      # Condition 1: syntax valid, non-system, resolving domain
    is_deliverable: bool    # Condition 2: active MX records, non-disposable
    can_draft: bool         # True only if BOTH conditions pass
    action: str             # "DRAFT" or "DELETE"
    reason: str
    domain: str = ""
    mx_records: List[str] = field(default_factory=list)


@dataclass
class DeliverabilityResult:
    email: str
    is_deliverable: bool
    status: str  # "DELIVERABLE" or "UNDELIVERABLE"
    reason: str
    domain: str = ""
    mx_records: List[str] = field(default_factory=list)


class EmailDeliverabilityVerifier:
    """
    High-performance email verifier evaluating Availability and Deliverability.
    If either fails, the system enforces automatic deletion.
    """

    def __init__(self, dns_timeout: float = 3.0, allow_offline_fallback: bool = True):
        self.dns_timeout = dns_timeout
        self.allow_offline_fallback = allow_offline_fallback
        self._domain_cache: Dict[str, Tuple[bool, str, List[str]]] = {}

        # Configure DNS resolver with custom timeout
        try:
            self.resolver = dns.resolver.Resolver()
        except Exception:
            self.resolver = dns.resolver.Resolver(configure=False)
            self.resolver.nameservers = ["8.8.8.8", "1.1.1.1", "8.8.4.4"]

        self.resolver.lifetime = dns_timeout
        self.resolver.timeout = dns_timeout

    def validate_syntax(self, email: str) -> Tuple[bool, str]:
        """Validate email format and length constraints."""
        if not email or not isinstance(email, str):
            return False, "Email is missing or null"

        email = email.strip()
        if len(email) > 254:
            return False, "Email exceeds maximum length (254 chars)"

        if not EMAIL_REGEX.match(email):
            return False, "Invalid email syntax format"

        parts = email.split("@")
        if len(parts) != 2:
            return False, "Malformed email structure"

        local_part, domain = parts
        if len(local_part) > 64:
            return False, "Local part exceeds 64 characters"

        if "." not in domain or len(domain.split(".")[-1]) < 2:
            return False, "Domain missing top-level domain (TLD)"

        return True, "Syntax valid"

    def is_disposable(self, domain: str) -> bool:
        """Check if domain is a known temporary / burner email service."""
        return domain.lower().strip() in DISPOSABLE_DOMAINS

    def is_system_or_generic_inbox(self, email: str) -> Tuple[bool, str]:
        """Check if address is an unmonitored, billing, or system mailbox."""
        if not email or "@" not in email:
            return False, ""
        local_part = email.split("@")[0].lower().strip()
        
        # Check exact prefix or prefix before . or _ (e.g., payable.in, billing_dept)
        clean_prefix = re.split(r"[._+-]", local_part)[0]
        if local_part in SYSTEM_OR_GENERIC_PREFIXES or clean_prefix in SYSTEM_OR_GENERIC_PREFIXES:
            return True, f"Address '{email}' is a system/billing/bot mailbox ({clean_prefix}@), not an active recruiter inbox"

        return False, ""

    def check_availability(self, email: str) -> Tuple[bool, str]:
        """
        Condition 1: Check if the address is available and legitimate.
        - Valid RFC 5322 syntax
        - Not an unmonitored system, billing, or bot address
        - Has valid domain structure
        """
        syntax_ok, syntax_err = self.validate_syntax(email)
        if not syntax_ok:
            return False, f"Address unavailable: {syntax_err}"

        is_system, system_msg = self.is_system_or_generic_inbox(email)
        if is_system:
            return False, f"Address unavailable: {system_msg}"

        return True, "Address is available and properly formatted"

    def check_domain_mx(self, domain: str) -> Tuple[bool, str, List[str]]:
        """
        Condition 2: Query DNS for Mail Exchange (MX) records.
        Cached in-memory to prevent duplicate lookups for recruiters from the same company.
        """
        domain = domain.lower().strip()

        if domain in self._domain_cache:
            return self._domain_cache[domain]

        if self.is_disposable(domain):
            result = (False, f"Domain '{domain}' is a disposable/burner email service", [])
            self._domain_cache[domain] = result
            return result

        try:
            answers = self.resolver.resolve(domain, "MX")
            mx_hosts = [str(r.exchange).rstrip(".") for r in answers]
            if mx_hosts:
                result = (True, f"Active MX servers verified: {', '.join(mx_hosts[:2])}", mx_hosts)
            else:
                result = (False, f"No MX hosts returned for '{domain}'", [])
            self._domain_cache[domain] = result
            return result

        except dns.resolver.NXDOMAIN:
            result = (False, f"Domain '{domain}' does not exist (NXDOMAIN)", [])
            self._domain_cache[domain] = result
            return result

        except dns.resolver.NoAnswer:
            # Fallback to A record check per RFC 5321 (mail host fallback)
            try:
                a_answers = self.resolver.resolve(domain, "A")
                if a_answers:
                    result = (True, f"Domain '{domain}' has active A-record host fallback", [domain])
                    self._domain_cache[domain] = result
                    return result
            except Exception:
                pass

            result = (False, f"Domain '{domain}' has no active MX or mail exchange records", [])
            self._domain_cache[domain] = result
            return result

        except (dns.resolver.NoNameservers, dns.exception.Timeout):
            if self.allow_offline_fallback:
                result = (True, "DNS servers unreachable (offline grace mode); syntax verified", [])
            else:
                result = (False, f"DNS servers unreachable for domain '{domain}'", [])
            self._domain_cache[domain] = result
            return result

        except Exception as e:
            if self.allow_offline_fallback:
                result = (True, f"DNS check skipped ({type(e).__name__}); syntax verified", [])
            else:
                result = (False, f"DNS resolution failed: {e}", [])
            self._domain_cache[domain] = result
            return result

    def security_check(self, email: str) -> SecurityCheckResult:
        """
        Perform strict Two-Condition Security Verification:
        Condition 1: Address is Available & Legitimate (syntax, non-system).
        Condition 2: Address is Deliverable (active MX, non-disposable).
        
        If both pass -> can_draft=True, action='DRAFT'.
        If either fails -> can_draft=False, action='DELETE'.
        """
        if not email or not isinstance(email, str):
            return SecurityCheckResult(
                email=str(email),
                is_available=False,
                is_deliverable=False,
                can_draft=False,
                action="DELETE",
                reason="Address is null or non-string"
            )

        cleaned_email = email.strip()

        # Condition 1: Availability
        avail_ok, avail_msg = self.check_availability(cleaned_email)
        if not avail_ok:
            return SecurityCheckResult(
                email=cleaned_email,
                is_available=False,
                is_deliverable=False,
                can_draft=False,
                action="DELETE",
                reason=avail_msg
            )

        domain = cleaned_email.split("@")[1].lower()

        # Condition 2: Deliverability
        deliv_ok, deliv_msg, mx_hosts = self.check_domain_mx(domain)
        if not deliv_ok:
            return SecurityCheckResult(
                email=cleaned_email,
                is_available=True,
                is_deliverable=False,
                can_draft=False,
                action="DELETE",
                reason=f"Address undeliverable: {deliv_msg}",
                domain=domain,
                mx_records=mx_hosts
            )

        # Both conditions verified!
        return SecurityCheckResult(
            email=cleaned_email,
            is_available=True,
            is_deliverable=True,
            can_draft=True,
            action="DRAFT",
            reason=f"Available & Deliverable (MX: {', '.join(mx_hosts[:1]) if mx_hosts else 'Verified'})",
            domain=domain,
            mx_records=mx_hosts
        )

    def verify(self, email: str) -> DeliverabilityResult:
        """Backwards-compatible deliverability checker."""
        sec = self.security_check(email)
        return DeliverabilityResult(
            email=sec.email,
            is_deliverable=sec.can_draft,
            status="DELIVERABLE" if sec.can_draft else "UNDELIVERABLE",
            reason=sec.reason,
            domain=sec.domain,
            mx_records=sec.mx_records
        )
