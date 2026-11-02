"""
Email Deliverability & MX Verification Engine
Validates syntax, disposable domains, and queries DNS for active Mail Exchange (MX) records.
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

# Standard RFC 5322 compliant email regex
EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)


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
    High-performance email deliverability verifier with in-memory domain caching,
    syntax validation, burner domain detection, and DNS MX resolution.
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
        return domain.lower() in DISPOSABLE_DOMAINS

    def check_domain_mx(self, domain: str) -> Tuple[bool, str, List[str]]:
        """
        Query DNS for Mail Exchange (MX) records.
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

    def verify(self, email: str) -> DeliverabilityResult:
        """
        Complete verification pipeline:
        1. Syntax validation
        2. Disposable domain check
        3. DNS MX record resolution
        """
        if not email or not isinstance(email, str):
            return DeliverabilityResult(
                email=str(email),
                is_deliverable=False,
                status="UNDELIVERABLE",
                reason="Email is empty or non-string"
            )

        cleaned_email = email.strip()
        syntax_ok, syntax_err = self.validate_syntax(cleaned_email)
        if not syntax_ok:
            return DeliverabilityResult(
                email=cleaned_email,
                is_deliverable=False,
                status="UNDELIVERABLE",
                reason=syntax_err
            )

        domain = cleaned_email.split("@")[1].lower()

        mx_ok, mx_msg, mx_hosts = self.check_domain_mx(domain)
        if not mx_ok:
            return DeliverabilityResult(
                email=cleaned_email,
                is_deliverable=False,
                status="UNDELIVERABLE",
                reason=mx_msg,
                domain=domain,
                mx_records=mx_hosts
            )

        return DeliverabilityResult(
            email=cleaned_email,
            is_deliverable=True,
            status="DELIVERABLE",
            reason=mx_msg,
            domain=domain,
            mx_records=mx_hosts
        )
