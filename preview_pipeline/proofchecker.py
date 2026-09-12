"""
Deterministic Sensitive Data Proofchecker ("Organisation" Mode)
Transmute System (SIH 2026 PS 26154)

Multi-layered offline scanner:
- Layer 1: High-Speed Multi-Keyword Automaton (Aho-Corasick with pure-Python trie fallback)
- Layer 2: Structured Regex Scanners (RFC 1918 IPv4, internal domains, secret tokens) + Defensive Citation Safeguards
- Layer 3: Shannon Entropy Calculation (H >= 4.2 for strings >= 20 chars)
- In-place HTML span wrapping: <span style="color: red; font-weight: bold;">[SENSITIVE: <matched_value>]</span>
"""

import re
import math
from collections import Counter, deque
from typing import Tuple, List, Optional, Set

try:
    import ahocorasick
    HAS_PYAHOCORASICK = True
except ImportError:
    ahocorasick = None
    HAS_PYAHOCORASICK = False

from .types import SensitiveDataFlag

# =============================================================================
# 250+ Kali / SecLists Operational Keywords & Sensitive Indicators
# =============================================================================
KALI_SECLISTS_KEYWORDS = [
    # ── 1. Auth, Credentials, Private Keys & Tokens (~105 keywords) ──
    "AUTHORIZATION",
    "BEARER",
    "BEGIN RSA PRIVATE KEY",
    "BEGIN PRIVATE KEY",
    "BEGIN OPENSSH PRIVATE KEY",
    "BEGIN DSA PRIVATE KEY",
    "BEGIN EC PRIVATE KEY",
    "BEGIN PGP PRIVATE KEY BLOCK",
    "BEGIN ENCRYPTED PRIVATE KEY",
    "BEGIN CERTIFICATE",
    "END RSA PRIVATE KEY",
    "END PRIVATE KEY",
    "END OPENSSH PRIVATE KEY",
    "END DSA PRIVATE KEY",
    "END EC PRIVATE KEY",
    "END PGP PRIVATE KEY BLOCK",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SESSION_TOKEN",
    "AWS_SECURITY_TOKEN",
    "ROOT_PASSWORD",
    "SSH_PRIVATE_KEY",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa_priv",
    "passwd",
    "shadow",
    "api_token",
    "api_secret",
    "api_key",
    "access_token",
    "refresh_token",
    "client_secret",
    "secret_key",
    "master_key",
    "private_key",
    "privkey",
    "encryption_key",
    "jwt_secret",
    "jwt_key",
    "database_password",
    "db_password",
    "db_pass",
    "admin_password",
    "admin_pass",
    "root_pass",
    "root_pwd",
    "ldap_password",
    "kerberos_ticket",
    "ntlm_hash",
    "sam_database",
    "lsass_dump",
    "mimikatz",
    "vault_token",
    "kubeconfig",
    "docker_auth",
    "htpasswd",
    "wp-config.php",
    "conn_string",
    "connection_string",
    "bearer_token",
    "oauth_token",
    "session_secret",
    "auth_token",
    "x-api-key",
    "x-auth-token",
    "x-amz-security-token",
    "slack_token",
    "discord_webhook",
    "sendgrid_api_key",
    "stripe_secret_key",
    "twilio_auth_token",
    "mailgun_api_key",
    "pagerduty_token",
    "datadog_api_key",
    "splunk_token",
    "newrelic_license_key",
    "firebase_secret",
    "algolia_api_key",
    "heroku_api_key",
    "circleci_token",
    "travis_token",
    "sonarqube_token",
    "vault_addr",
    "consul_token",
    "etcd_root_password",
    "rabbitmq_password",
    "redis_password",
    "postgres_password",
    "mysql_password",
    "sql_password",
    "oracle_sys_password",
    "mongodb_secret",
    "s3_access_key",
    "azure_client_secret",
    "gcp_service_account",
    "privkey.pem",
    "server.key",
    "ca.key",
    "client.key",
    "keystore.jks",
    "cert.pfx",
    "client.p12",
    "secring.gpg",
    "gpg_secret_key",
    "seed_phrase",
    "bip39_mnemonic",
    "wallet_private_key",
    "totp_secret",
    "mfa_secret",
    "otp_secret",
    "backup_codes",
    "recovery_key",
    "passphrase",
    "hardware_token_seed",
    "yubikey_secret",
    "okta_api_token",
    "onelogin_token",
    "ping_identity_secret",
    "azuread_app_secret",
    "entraid_client_secret",
    "jira_pat_token",
    "confluence_pat",
    "github_pat",
    "gitlab_pat",
    "bitbucket_app_password",
    "kms_key_secret",
    "keyvault_secret",

    # ── 2. Operational & Clearance Markings (~62 keywords) ──
    "TOP SECRET",
    "NOFORN",
    "RESTRICTED OPERATION",
    "LAW ENFORCEMENT SENSITIVE",
    "SECRET//SI",
    "INTERNAL EYES ONLY",
    "SECRET//NOFORN",
    "TOP SECRET//SCI",
    "TOP SECRET//SI",
    "TOP SECRET//TK",
    "TOP SECRET//NOFORN",
    "SECRET//REL TO",
    "CONFIDENTIAL//REL TO",
    "CONFIDENTIAL//NOFORN",
    "ORCON",
    "PROPIN",
    "FOUO",
    "FOR OFFICIAL USE ONLY",
    "RESTRICTED DATA",
    "FORMERLY RESTRICTED DATA",
    "COMSEC",
    "SIGINT",
    "HUMINT",
    "GEOINT",
    "MASINT",
    "SPECIAL ACCESS REQUIRED",
    "SAP/SAR",
    "OPERATION SHADOWGATE INTERNAL",
    "INTERNAL ONLY - NOT FOR PUBLIC",
    "STRICTLY CONFIDENTIAL",
    "CUI//SP-SENS",
    "CUI//PRIV",
    "DEA SENSITIVE",
    "FIN INTEL SECRET",
    "TALENT KEYHOLE",
    "GAMMA COMPARTMENT",
    "HCS CLEARANCE",
    "SI COMPARTMENT",
    "TK CLEARANCE",
    "NO DISSEM",
    "CLASSIFIED COMPARTMENT",
    "SEALED INDICTMENT",
    "WIRETAP RECORD",
    "WARRANT IDENTIFIER",
    "RAW SURVEILLANCE LOG",
    "INTERCEPT TRANSCRIPT",
    "UNDERCOVER ALIAS",
    "WITNESS PROTECTION ID",
    "INFORMANT CODE",
    "WHISTLEBLOWER ID",
    "SUBPOENA NOTICE INTERNAL",
    "TAKEDOWN NOTICE INTERNAL",
    "LIMITED DISTRIBUTION",
    "SENSITIVE BUT UNCLASSIFIED",
    "LES/NF",
    "SECRET//ORCON",
    "TOP SECRET//SPECIAL HANDLING",
    "RESTRICTED DISSEMINATION",
    "NOT FOR DISTRIBUTION",
    "CONFIDENTIAL ATTORNEY CLIENT",
    "PRIVILEGED AND CONFIDENTIAL",

    # ── 3. Threat Intel Sensitive Identifiers & Infrastructure (~60 keywords) ──
    "DEFANGED_IOC",
    "IMMEDIATE_TAKEDOWN",
    "HONEYPOT_BASTION",
    "INTERNAL_C2_SINKHOLE",
    "SINKHOLE_AGENT",
    "BASTION_GATEWAY",
    "CANARY_TOKEN",
    "COBALT_STRIKE_BEACON",
    "BURP_COLLABORATOR",
    "INTERACTSH",
    "SANGFOR_INTERNAL",
    "TITAN_SENSOR",
    "INTERNAL_TELEMETRY_PIPELINE",
    "DARKNET_DROP",
    "RED_TEAM_STAGING",
    "AIRGAP_BRIDGE",
    "EXFIL_DROPZONE",
    "IMPLANT_UUID",
    "BACKDOOR_KEY",
    "MALWARE_SAMPLE_UNSTRIPPED",
    "ZERO_DAY_EXPLOIT",
    "CORE_DB_PROD",
    "BANK_HSM",
    "DC_INTERNAL_AUTH",
    "C2_INFRASTRUCTURE_SECRET",
    "COVERT_CHANNEL_KEY",
    "COVERT_ASSET_ID",
    "SAFEHOUSE_LOCATION",
    "EXFIL_SERVER_IP",
    "STAGING_BASTION_HOST",
    "INTERNAL_JUMP_SERVER",
    "ISOLATED_ENCLAVE_HOST",
    "PRODUCTION_HSM_ENDPOINT",
    "PKI_ROOT_CA_BUNDLE",
    "INTERNAL_PKI_PRIVKEY",
    "CODE_SIGNING_PRIVKEY",
    "INTERNAL_DNS_ROOT",
    "INTERNAL_PROXY_BYPASS",
    "SANDBOX_EVASION_TRIGGER",
    "KILLSWITCH_DOMAIN",
    "MUTEX_INDICATOR",
    "COMMAND_AND_CONTROL_NODE",
    "EXPLOIT_PAYLOAD_DROPPER",
    "STAGER_SHELLCODE",
    "REFLECTIVE_DLL_INJECTION",
    "PROCESS_HOLLOWING_TARGET",
    "ROOTKIT_HOOK",
    "BOOTKIT_SECTOR",
    "FIRMWARE_BACKDOOR",
    "VULNERABILITY_RESEARCH_INTERNAL",
    "ZERO_CLICK_CHAIN",
    "TAO_CATALOG_ID",
    "PEGASUS_IMPLANT",
    "PRE_AUTH_RCE",
    "CRITICAL_INFRASTRUCTURE_TARGET",
    "SCADA_CONTROLLER_KEY",
    "PLC_FIRMWARE_KEY",
    "OT_NETWORK_ENCLAVE",
    "SAFETY_SYSTEM_OVERRIDE",

    # ── 4. Kali / SecLists Artifacts, Hives, and Hashes (~48 keywords) ──
    "/etc/passwd",
    "/etc/shadow",
    "/etc/sudoers",
    "/etc/gshadow",
    "/etc/master.passwd",
    "authorized_keys",
    "known_hosts",
    "id_rsa.pub",
    ".bash_history",
    ".zsh_history",
    "SAM_HIVE",
    "SYSTEM_HIVE",
    "NTDS.DIT",
    "SECURITY_HIVE",
    "admin_hash",
    "root_hash",
    "user_hash",
    "password_hash",
    "hashcat_potfile",
    "john_potfile",
    "responder_session",
    "ntlmv2_response",
    "smb_relay_hash",
    "bloodhound_db",
    "sharphound_cache",
    "rubeus_ticket",
    "psexec_svc",
    "wmiexec_output",
    "impacket_session",
    "sqlmap_dump",
    "nmap_secret_output",
    "nessus_credential_dump",
    "metasploit_db",
    "meterpreter_session",
    "empire_stager",
    "havoc_demon",
    "sliver_beacon",
    "mythic_payload",
    "covenant_grunt",
    "brute_ratel_badger",
    "poshc2_implant",
    "shad0w_beacon",
    "koadic_zombie",
    "powershell_empire",
    "golden_ticket",
    "silver_ticket",
    "skeleton_key",
    "asreproast",
    "kerberoast",
    "dcsync",
    "netntlmv2",
    "bcrypt_hash",
    "argon2_hash",
]


# =============================================================================
# Pure-Python Aho-Corasick Trie Fallback
# =============================================================================
class _AhoNode:
    __slots__ = ("children", "fail", "outputs")

    def __init__(self):
        self.children = {}
        self.fail = None
        self.outputs = []  # List of (keyword, entity_type)


class PurePythonAhoCorasick:
    """High-speed pure-Python Aho-Corasick automaton."""

    def __init__(self):
        self.root = _AhoNode()
        self._built = False

    def add_keyword(self, keyword: str, entity_type: str = "TACTICAL_KEYWORD"):
        node = self.root
        for ch in keyword.lower():
            if ch not in node.children:
                node.children[ch] = _AhoNode()
            node = node.children[ch]
        node.outputs.append((keyword, entity_type))
        self._built = False

    def build(self):
        queue = deque()
        for ch, child in self.root.children.items():
            child.fail = self.root
            queue.append(child)

        while queue:
            curr = queue.popleft()
            for ch, child in curr.children.items():
                queue.append(child)
                fail_node = curr.fail
                while fail_node is not None and ch not in fail_node.children:
                    fail_node = fail_node.fail
                child.fail = fail_node.children[ch] if fail_node else self.root
                if child.fail.outputs:
                    child.outputs.extend(child.fail.outputs)
        self._built = True

    def search(self, text: str):
        if not self._built:
            self.build()
        curr = self.root
        text_lower = text.lower()
        for idx, ch in enumerate(text_lower):
            while curr is not None and ch not in curr.children:
                curr = curr.fail
            curr = curr.children[ch] if curr else self.root
            if curr.outputs:
                for kw, entity_type in curr.outputs:
                    start = idx - len(kw) + 1
                    end = idx + 1
                    yield (start, end, text[start:end], entity_type)


class AhoCorasickMatcher:
    """Wrapper that chooses C-extension pyahocorasick if available, else pure-Python trie."""

    def __init__(self):
        self.use_c_extension = HAS_PYAHOCORASICK
        if self.use_c_extension:
            self.automaton = ahocorasick.Automaton()
        else:
            self.automaton = PurePythonAhoCorasick()
        self._built = False

    def add_keyword(self, keyword: str, entity_type: str = "TACTICAL_KEYWORD"):
        if self.use_c_extension:
            self.automaton.add_word(keyword.lower(), (keyword, entity_type))
        else:
            self.automaton.add_keyword(keyword, entity_type)
        self._built = False

    def build(self):
        if self.use_c_extension:
            self.automaton.make_automaton()
        else:
            self.automaton.build()
        self._built = True

    def search(self, text: str):
        if not self._built:
            self.build()
        if self.use_c_extension:
            text_lower = text.lower()
            for end_idx, (kw, entity_type) in self.automaton.iter(text_lower):
                start = end_idx - len(kw) + 1
                end = end_idx + 1
                yield (start, end, text[start:end], entity_type)
        else:
            yield from self.automaton.search(text)


# =============================================================================
# Helper Utilities
# =============================================================================
def _is_word_boundary(text: str, start: int, end: int) -> bool:
    """Check if substring match is properly bounded to avoid mid-word false positives."""
    if text[start].isalnum() or text[start] == "_":
        if start > 0 and (text[start - 1].isalnum() or text[start - 1] == "_"):
            return False
    if text[end - 1].isalnum() or text[end - 1] == "_":
        if end < len(text) and (text[end].isalnum() or text[end] == "_"):
            return False
    return True


def _is_valid_ipv4(ip_str: str) -> bool:
    """Verify that all octets are integers between 0 and 255."""
    parts = ip_str.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(part) <= 255 for part in parts)
    except ValueError:
        return False


# Regex to protect citation markers like [^src-1], [^aud-2], [^vid-3], [^doc-4], [^fact-5]
CITATION_REGEX = re.compile(r"\[\^(?:src|aud|vid|doc|fact|[a-zA-Z0-9_\-]+)\]", re.IGNORECASE)

# Regex to identify already-wrapped sensitive spans
EXISTING_WRAPPER_REGEX = re.compile(
    r'<span style="color: red; font-weight: bold;">\[SENSITIVE:[^\]]+\]</span>|\[SENSITIVE:[^\]]+\]',
    re.IGNORECASE,
)

# Standalone citation tokens that should never be flagged
SAFE_CITATION_TOKEN_REGEX = re.compile(r"^(?:src|aud|vid|doc|fact)-\d+$", re.IGNORECASE)


# =============================================================================
# Deterministic Sensitivity Scanner
# =============================================================================
class DeterministicSensitivityScanner:
    """
    Multi-stage deterministic sensitive data scanner:
    - Layer 1: High-Speed Multi-Keyword Automaton (Aho-Corasick)
    - Layer 2: Structured Regex Scanners (RFC 1918 Private IPv4, Internal Domains, Secret Tokens)
    - Layer 3: Shannon Entropy Calculation (H >= 4.2 for strings >= 20 chars)
    """

    def __init__(self):
        # Layer 1: Aho-Corasick Pattern Matcher
        self.matcher = AhoCorasickMatcher()
        for kw in KALI_SECLISTS_KEYWORDS:
            self.matcher.add_keyword(kw, "TACTICAL_KEYWORD")
        self.matcher.build()

        # Layer 2: Structured Regex Scanners
        self.rfc1918_regex = re.compile(
            r"\b(10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|127\.\d{1,3}\.\d{1,3}\.\d{1,3})\b"
        )
        self.internal_domain_regex = re.compile(
            r"\b([a-zA-Z0-9_\-\.]+\.(?:internal|local|corp|lan|intranet|ntro))\b",
            re.IGNORECASE,
        )
        self.secret_token_regex = re.compile(
            r"\b([a-zA-Z0-9_\-]{32,64})\b"
        )
        self.header_secret_regex = re.compile(
            r"(?i)\b(?:bearer|token|secret|session|key|auth|api[_-]?key|auth[_-]?token)\s*[:=]\s*[\"']?([a-zA-Z0-9_\-]{32,64})[\"']?"
        )
        self.db_conn_regex = re.compile(
            r"(?:postgresql|mysql|mongodb|redis)://[^:\s]+:[^@\s]+@[^/\s]+"
        )
        self.exploit_regex = re.compile(
            r"(?:\\x[0-9a-fA-F]{2}){4,}|\b(?:curl|wget)\s+[^|\n]+(?:\|\s*(?:bash|sh))\b"
        )
        self.internal_pii_regex = re.compile(
            r"\b(EMP-[0-9]{4,8}|UID-[0-9]{4,8})\b"
        )

        # Layer 3: Standalone alphanumeric tokens for Shannon entropy evaluation
        self.alphanumeric_candidate_regex = re.compile(r"\b([a-zA-Z0-9]{20,})\b")

    @staticmethod
    def calculate_shannon_entropy(token: str) -> float:
        """
        Calculate Shannon entropy of a string:
        H(X) = - sum(p(x) * log2(p(x)))
        """
        if not token:
            return 0.0
        length = len(token)
        counts = Counter(token)
        return -sum((count / length) * math.log2(count / length) for count in counts.values())

    def _get_protected_spans(self, text: str) -> List[Tuple[int, int]]:
        """Identify spans that must never be modified (citations, already wrapped markers)."""
        protected = []
        for m in CITATION_REGEX.finditer(text):
            protected.append((m.start(), m.end()))
        for m in EXISTING_WRAPPER_REGEX.finditer(text):
            protected.append((m.start(), m.end()))
        return protected

    def _overlaps_any(self, start: int, end: int, spans: List[Tuple[int, int]]) -> bool:
        """Check if [start, end) intersects any range in spans."""
        for s, e in spans:
            if max(start, s) < min(end, e):
                return True
        return False

    def scan(self, text: str) -> List[SensitiveDataFlag]:
        """Scan text and return detected sensitive flags without text modification."""
        _, flags = self.scan_and_redact(text)
        return flags

    def scan_and_redact(self, text: str) -> Tuple[str, List[SensitiveDataFlag]]:
        """
        Scan text for sensitive data patterns and wrap matches in red HTML spans:
        <span style="color: red; font-weight: bold;">[SENSITIVE: <matched_value>]</span>

        Guarantees:
        - Citations ([^src-X], [^aud-X]) are 100% untouched.
        - Sub-10ms deterministic execution.
        - Idempotent: already-wrapped items are not double-wrapped.
        - Deduplicated non-overlapping flagged spans.
        """
        if not text:
            return text or "", []

        protected_spans = self._get_protected_spans(text)
        candidates = []  # List of (start, end, entity_type, matched_text, priority)

        # ─────────────────────────────────────────────────────────────────
        # Layer 1: High-Speed Multi-Keyword Automaton (Aho-Corasick)
        # Priority: 1 (Highest keyword priority)
        # ─────────────────────────────────────────────────────────────────
        for start, end, matched_text, entity_type in self.matcher.search(text):
            if self._overlaps_any(start, end, protected_spans):
                continue
            if SAFE_CITATION_TOKEN_REGEX.match(matched_text):
                continue
            if not _is_word_boundary(text, start, end):
                continue
            candidates.append((start, end, entity_type, matched_text, 1))

        # ─────────────────────────────────────────────────────────────────
        # Layer 2: Structured Regex Scanners
        # Priority: 2
        # ─────────────────────────────────────────────────────────────────
        # 2a. RFC 1918 Private IPv4
        for m in self.rfc1918_regex.finditer(text):
            start, end = m.span()
            matched_text = m.group(0)
            if self._overlaps_any(start, end, protected_spans):
                continue
            if not _is_valid_ipv4(matched_text):
                continue
            candidates.append((start, end, "INTERNAL_IP", matched_text, 2))

        # 2b. Internal Domain Zones
        for m in self.internal_domain_regex.finditer(text):
            start, end = m.span()
            matched_text = m.group(0)
            if self._overlaps_any(start, end, protected_spans):
                continue
            candidates.append((start, end, "INTERNAL_DOMAIN", matched_text, 2))

        # 2c. Header Secret Tokens & Hex Hashes
        for m in self.header_secret_regex.finditer(text):
            token = m.group(1)
            start = m.start(1)
            end = m.end(1)
            if self._overlaps_any(start, end, protected_spans):
                continue
            if SAFE_CITATION_TOKEN_REGEX.match(token):
                continue
            candidates.append((start, end, "SECRET_TOKEN", token, 2))

        for m in self.secret_token_regex.finditer(text):
            start, end = m.span()
            token = m.group(0)
            if self._overlaps_any(start, end, protected_spans):
                continue
            if SAFE_CITATION_TOKEN_REGEX.match(token):
                continue
            # Check if token is hex hash or has high entropy (>= 3.8)
            is_hex = bool(re.fullmatch(r"[0-9a-fA-F]{32,64}", token))
            if is_hex or self.calculate_shannon_entropy(token) >= 3.8:
                candidates.append((start, end, "SECRET_TOKEN", token, 2))

        # 2d. Database Connection Strings
        for m in self.db_conn_regex.finditer(text):
            start, end = m.span()
            matched_text = m.group(0)
            if self._overlaps_any(start, end, protected_spans):
                continue
            candidates.append((start, end, "DB_CONNECTION_STRING", matched_text, 2))

        # 2e. Exploit Payloads
        for m in self.exploit_regex.finditer(text):
            start, end = m.span()
            matched_text = m.group(0)
            if self._overlaps_any(start, end, protected_spans):
                continue
            candidates.append((start, end, "EXPLOIT_PAYLOAD", matched_text, 2))

        # 2f. Internal PII
        for m in self.internal_pii_regex.finditer(text):
            start, end = m.span()
            matched_text = m.group(0)
            if self._overlaps_any(start, end, protected_spans):
                continue
            candidates.append((start, end, "INTERNAL_PII", matched_text, 2))

        # ─────────────────────────────────────────────────────────────────
        # Layer 3: Shannon Entropy Calculation
        # Priority: 3
        # Flag standalone alphanumeric strings of length >= 20 with H(X) >= 4.2
        # ─────────────────────────────────────────────────────────────────
        for m in self.alphanumeric_candidate_regex.finditer(text):
            token = m.group(0)
            start, end = m.span()
            if self._overlaps_any(start, end, protected_spans):
                continue
            if SAFE_CITATION_TOKEN_REGEX.match(token):
                continue
            entropy = self.calculate_shannon_entropy(token)
            if entropy >= 4.2:
                candidates.append((start, end, "HIGH_ENTROPY_SECRET", token, 3))

        # ─────────────────────────────────────────────────────────────────
        # Overlap Resolution & Deduplication
        # Longer matches take precedence, followed by priority (Layer 1 > Layer 2 > Layer 3)
        # ─────────────────────────────────────────────────────────────────
        # Sort: length descending, priority ascending, start ascending
        sorted_candidates = sorted(
            candidates, key=lambda c: (-(c[1] - c[0]), c[4], c[0])
        )

        selected_spans = []
        for cand in sorted_candidates:
            start, end, entity_type, matched_text, prio = cand
            # Check if this candidate overlaps with any already selected span
            overlap = False
            for s_start, s_end, _, _, _ in selected_spans:
                if max(start, s_start) < min(end, s_end):
                    overlap = True
                    break
            if not overlap:
                selected_spans.append(cand)

        # Sort selected matches by start position ascending for the output flags
        selected_spans.sort(key=lambda c: c[0])

        flags: List[SensitiveDataFlag] = [
            SensitiveDataFlag(
                entity_type=etype,
                matched_text=mtext,
                char_start=start,
                char_end=end,
                severity="HIGH",
            )
            for start, end, etype, mtext, _ in selected_spans
        ]

        # ─────────────────────────────────────────────────────────────────
        # In-Place Text Wrapping (reverse order to preserve char offsets)
        # ─────────────────────────────────────────────────────────────────
        redacted_text = text
        for start, end, _, matched_text, _ in sorted(
            selected_spans, key=lambda c: c[0], reverse=True
        ):
            wrapper = f'<span style="color: red; font-weight: bold;">[SENSITIVE: {matched_text}]</span>'
            redacted_text = redacted_text[:start] + wrapper + redacted_text[end:]

        return redacted_text, flags


# =============================================================================
# Module-level exports & singleton instance
# =============================================================================
_default_scanner = DeterministicSensitivityScanner()


def scan_and_redact(text: str) -> Tuple[str, List[SensitiveDataFlag]]:
    """Convenience module-level function for scanning and wrapping sensitive data."""
    return _default_scanner.scan_and_redact(text)


def calculate_shannon_entropy(token: str) -> float:
    """Convenience module-level function for calculating Shannon entropy."""
    return DeterministicSensitivityScanner.calculate_shannon_entropy(token)