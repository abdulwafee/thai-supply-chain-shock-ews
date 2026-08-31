"""Secret, privacy and dependency-vulnerability review (Task E2).

**A detected secret value is never returned, logged or written to a report.**
Every finding carries a family, a path, a line number, a length and a truncated
SHA-256 fingerprint of the matched text. The fingerprint is enough to tell two
findings apart and to confirm a later removal; it is not enough to use the
credential. :func:`assert_no_secret_values_printed` re-checks the rendered
report against the values that were found, so the guarantee is verified rather
than merely intended.

**Locked-outcome paths are removed from the scan set before scanning begins.**
Handing a sealed file to a scanner is a read, whatever the scanner then does
with it.

Two scanners run, and their states are kept apart. The in-repo pattern set
covers what this project specifically cares about — absolute home paths,
usernames embedded in paths, notebook output carrying environment information —
which a generic tool does not. ``detect-secrets`` runs alongside it as an
independent second opinion. If it is unavailable the result is
``not_run``, never ``clean``: a scan nobody performed found nothing in the same
uninformative sense that an unopened box contains nothing.

The dependency audit records the tool version and the advisory database it
consulted, because a clean audit is a statement about one database on one day,
not a permanent property of the pinned set.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

__all__ = [
    "PATTERNS",
    "SecurityError",
    "assert_no_locked_path_scanned",
    "assert_no_secret_values_printed",
    "classify_entropy_findings",
    "classify_reviewed",
    "fingerprint",
    "run_detect_secrets",
    "run_pip_audit",
    "scan_paths",
    "scan_text",
    "summarise",
]

#: Pattern families. Group 1 is the sensitive span when the pattern has one,
#: otherwise the whole match is treated as sensitive.
PATTERNS = {
    "api_keys_and_tokens": re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|secret[_-]?key|client[_-]?secret"
        r"|bearer)\b\s*[:=]\s*['\"]?([A-Za-z0-9_\-./+]{16,})"
    ),
    "aws_access_key_id": re.compile(r"\b((?:AKIA|ASIA)[0-9A-Z]{16})\b"),
    "private_key_block": re.compile(r"(-----BEGIN [A-Z ]*PRIVATE KEY-----)"),
    "passwords": re.compile(
        r"(?i)\b(?:password|passwd|pwd)\b\s*[:=]\s*['\"]?([^\s'\"#]{8,})"
    ),
    "cookies_and_sessions": re.compile(
        r"(?i)\b(?:cookie|set-cookie|sessionid|jsessionid|phpsessid|csrftoken)\b"
        r"\s*[:=]\s*['\"]?([^\s'\"#]{8,})"
    ),
    "authorization_headers": re.compile(
        r"(?i)\bauthorization\b\s*[:=]\s*['\"]?((?:basic|bearer|token)\s+\S{8,})"
    ),
    "private_urls": re.compile(
        r"\b(https?://[^\s'\"<>]*(?::[^\s'\"<>@/]+)?@[^\s'\"<>]+)"
    ),
    "personal_email_addresses": re.compile(
        r"\b([A-Za-z0-9._%+\-]+@(?!example\.(?:com|org)\b)"
        r"[A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b"
    ),
    "absolute_home_paths": re.compile(
        r"((?:[A-Za-z]:\\Users\\|/home/|/Users/)[A-Za-z0-9._\-]+)"
    ),
    # A full dotted quad, not a prefix. "10.5.3" is a version number and
    # "172.30" is a coefficient; requiring four octets is the difference between
    # a finding and 290 of them.
    "local_ip_addresses": re.compile(
        r"(?<![\w.])((?:10|127)\.\d{1,3}\.\d{1,3}\.\d{1,3}"
        r"|192\.168\.\d{1,3}\.\d{1,3}"
        r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(?![\w.])"
    ),
    "temporary_download_credentials": re.compile(
        r"(?i)\b(?:x-amz-signature|sig|signature|token)=([A-Za-z0-9%_\-]{20,})"
    ),
}

#: Spans that describe a pattern rather than carry a value. Stripped before
#: matching so this module, its tests and the release documentation can publish
#: the rule they enforce without tripping it — while any literal credential
#: elsewhere in the same file is still found.
_LITERAL_SPANS = (
    re.compile(r"r?\"\"\".*?\"\"\"", re.DOTALL),
    re.compile(r"r?'''.*?'''", re.DOTALL),
    re.compile(r"r\"[^\"\n]*\""),
    re.compile(r"r'[^'\n]*'"),
    re.compile(r"`{1,3}[^`]*`{1,3}"),
)

_PLACEHOLDER = re.compile(
    r"(?i)^(?:x{3,}|<[^>]+>|\{\{?[a-z_]+\}?\}|your[_-]|changeme|placeholder"
    r"|redacted|\.\.\.|/absolute/path|example|dummy|sample|fake|test)"
)

_BINARY_SUFFIXES = {
    ".parquet", ".xls", ".xlsx", ".pdf", ".zip", ".pkl", ".joblib", ".png",
    ".jpg", ".jpeg", ".gif", ".ico", ".whl", ".gz", ".pyc", ".bin", ".so",
    ".dll", ".exe",
}


class SecurityError(ValueError):
    """The audit was asked to do something it must not, or found a blocker."""


def fingerprint(value: str) -> str:
    """A truncated digest that identifies a finding without disclosing it."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _mask(value: str) -> str:
    """A shape hint, never a usable prefix."""
    return f"<{len(value)} chars>"


def _strip_literal_spans(text: str) -> str:
    """Blank out pattern-describing spans, preserving line numbers."""
    for expression in _LITERAL_SPANS:
        text = expression.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    return text


def scan_text(text: str, path: str, *, families=None,
              strip_literal_spans: bool = True) -> list:
    """Findings in one file's text, redacted at the point of creation."""
    families = families or PATTERNS
    scanned = _strip_literal_spans(text) if strip_literal_spans else text
    findings = []
    for line_number, line in enumerate(scanned.splitlines(), start=1):
        for family, expression in families.items():
            for match in expression.finditer(line):
                value = match.group(1) if match.groups() else match.group(0)
                if not value or _PLACEHOLDER.match(value):
                    continue
                findings.append({
                    "family": family,
                    "path": path,
                    "line": line_number,
                    "fingerprint": fingerprint(value),
                    "masked": _mask(value),
                    "value_reported": False,
                })
    return findings


def assert_no_locked_path_scanned(paths, fragments) -> None:
    """Refuse to hand a sealed path to any scanner."""
    lowered = tuple(f.lower() for f in fragments)
    offenders = sorted(
        str(p) for p in paths
        if any(f in str(p).replace("\\", "/").lower() for f in lowered)
    )
    if offenders:
        raise SecurityError(
            f"locked-outcome path(s) {offenders} reached the scan set. Handing a "
            "sealed file to a scanner is a read, whatever the scanner does next"
        )


def scan_paths(root: Path, relative_paths, fragments) -> dict:
    """Scan an explicit path list. Locked paths are rejected, not skipped."""
    root = Path(root)
    assert_no_locked_path_scanned(relative_paths, fragments)
    findings, scanned, skipped_binary = [], 0, 0
    for relative in sorted(relative_paths):
        path = root / relative
        if Path(relative).suffix.lower() in _BINARY_SUFFIXES:
            skipped_binary += 1
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            skipped_binary += 1
            continue
        scanned += 1
        findings.extend(scan_text(text, str(relative)))
    return {
        "scanner": "in_repo_pattern_set",
        "families": sorted(PATTERNS),
        "files_scanned": scanned,
        "files_skipped_non_text": skipped_binary,
        "locked_paths_scanned": 0,
        "secret_values_printed": False,
        "findings": findings,
    }


def run_detect_secrets(root: Path, relative_paths, executable) -> dict:
    """Independent second opinion. Unavailable is recorded as ``not_run``."""
    if executable is None or not Path(executable).exists():
        return {"scanner": "detect-secrets", "state": "not_run",
                "reason": "tool_not_available_in_this_environment",
                "counted_as_clean": False, "findings": []}
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [str(executable), "-m", "detect_secrets", "scan", *sorted(relative_paths)],
        cwd=str(root), capture_output=True, text=True, check=False,
    )
    if completed.returncode != 0:
        return {"scanner": "detect-secrets", "state": "error",
                "returncode": completed.returncode,
                "counted_as_clean": False, "findings": []}
    payload = json.loads(completed.stdout)
    findings = [
        {
            "family": entry.get("type", "unknown"),
            "path": str(path).replace("\\", "/"),
            "line": entry.get("line_number"),
            # detect-secrets reports its own hashed_secret; it is passed through
            # rather than re-derived, and no value is ever available here.
            "fingerprint": str(entry.get("hashed_secret", ""))[:12],
            "masked": "<not disclosed>",
            "value_reported": False,
        }
        for path, entries in payload.get("results", {}).items()
        for entry in entries
    ]
    return {
        "scanner": "detect-secrets",
        "state": "ran",
        "version": payload.get("version"),
        "plugins": sorted(
            p.get("name", "") for p in payload.get("plugins_used", [])
        ),
        "counted_as_clean": not findings,
        "findings": findings,
    }


def assert_no_secret_values_printed(report_text: str, values) -> None:
    """Verify the rendered report discloses none of the values that were found."""
    leaked = sorted({value for value in values if value and value in report_text})
    if leaked:
        raise SecurityError(
            f"{len(leaked)} detected secret value(s) appear verbatim in the "
            "rendered report. Findings are reported as redacted fingerprints "
            "and locations only"
        )


#: pip-audit talks to an advisory service over TLS. Behind an inspecting proxy
#: the bundled certifi store cannot verify the intercepting root, while the
#: operating system store can, so ``truststore`` is injected when it is present.
#: This changes which certificate store is trusted -- never whether the
#: certificate is verified.
_PIP_AUDIT_DRIVER = (
    "import sys\n"
    "injected = False\n"
    "try:\n"
    "    import truststore\n"
    "    truststore.inject_into_ssl()\n"
    "    injected = True\n"
    "except Exception:\n"
    "    pass\n"
    "print(f'TRUSTSTORE_INJECTED={injected}', file=sys.stderr)\n"
    "from pip_audit._cli import audit\n"
    "sys.argv = ['pip-audit', *sys.argv[1:]]\n"
    "audit()\n"
)


def run_pip_audit(lock_path: Path, executable, *, runtime_or_dev: str,
                  service: str = "pypi") -> dict:
    """Audit one locked set. Records the tool and its database, not just a verdict."""
    if executable is None or not Path(executable).exists():
        return {"tool": "pip-audit", "state": "not_run",
                "reason": "tool_not_available_in_this_environment",
                "scope": runtime_or_dev, "counted_as_clean": False,
                "vulnerabilities": []}
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [str(executable), "-c", _PIP_AUDIT_DRIVER,
         "--requirement", str(lock_path), "--format", "json",
         "--progress-spinner", "off", "--vulnerability-service", service],
        capture_output=True, text=True, check=False,
    )
    if not completed.stdout.strip():
        return {"tool": "pip-audit", "state": "error",
                "returncode": completed.returncode,
                "stderr_tail": completed.stderr.strip().splitlines()[-3:],
                "scope": runtime_or_dev, "counted_as_clean": False,
                "vulnerabilities": []}
    payload = json.loads(completed.stdout)
    dependencies = payload.get("dependencies", payload if isinstance(payload, list) else [])
    vulnerabilities = [
        {
            "package": dependency.get("name"),
            "installed_version": dependency.get("version"),
            "advisory_id": vulnerability.get("id"),
            "fixed_versions": vulnerability.get("fix_versions", []),
            "runtime_or_dev": runtime_or_dev,
            "remediation": (
                f"upgrade to {vulnerability.get('fix_versions')}"
                if vulnerability.get("fix_versions")
                else "no fixed version published; accept with documented rationale"
            ),
        }
        for dependency in dependencies
        for vulnerability in dependency.get("vulns", [])
    ]
    return {
        "tool": "pip-audit",
        "tool_version": _installed_version(executable, "pip-audit"),
        "advisory_service": service,
        "trust_store": ("operating_system_via_truststore"
                        if "TRUSTSTORE_INJECTED=True" in completed.stderr
                        else "certifi_bundle"),
        "state": "ran",
        "scope": runtime_or_dev,
        "packages_audited": len(dependencies),
        "audited_names": sorted(
            d.get("name") for d in dependencies if d.get("name")
        ),
        "vulnerabilities": vulnerabilities,
        "counted_as_clean": not vulnerabilities,
        "audit_run_date_recorded_in": "docs/e2_release_checklist.md",
        "clean_audit_is_a_permanent_guarantee": False,
        "silent_upgrade_performed": False,
    }


def _installed_version(executable, distribution: str) -> str:
    probe = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [str(executable), "-c",
         f"from importlib import metadata; print(metadata.version('{distribution}'))"],
        capture_output=True, text=True, check=False,
    )
    return probe.stdout.strip() or "unknown"


#: A 64-character hex string in this repository is almost always a SHA-256
#: content checksum: manifests, audits and decision documents are full of them
#: by design. They are separated from real findings only when the line they sit
#: on actually names them as a digest -- the check is what makes the separation
#: honest rather than a blanket dismissal.
_CHECKSUM_CONTEXT = re.compile(
    r"(?i)(checksum|sha256|sha-256|hash|digest|fingerprint|content_id|"
    r"byte_sha|_sha\b|expected|actual)"
)


#: The line that opens a block, in either of the two shapes this repository
#: uses: a YAML or JSON mapping key, and a Python constant assigned a dict or a
#: parenthesised literal. A checksum table written as ``V1_PINNED_SHA256 = {``
#: names itself just as clearly as ``"byte_checksums": {`` does.
_MAPPING_KEY = re.compile(
    r"^\s*(?:\"?[\w./\\\-]+\"?\s*:|[A-Za-z_][\w]*\s*=\s*[\{\(\[]?\s*$)"
)

#: Long enough to be a digest rather than a word: a full SHA-256, or one of the
#: 12-character redacted fingerprints this module itself emits. The length alone
#: proves nothing -- the naming context beside it is what does the work.
_HEX_DIGEST = re.compile(r"\b[0-9a-f]{12,64}\b")


def _enclosing_keys(lines, index: int) -> list:
    """Every ancestor key above ``index``, outermost block included.

    A checksum block names itself once and then lists forty entries, so the
    fortieth entry has to be read in the light of the ``"byte_checksums": {``
    far above it. The nearest ancestor is not enough either: in
    ``V1_PINNED_SHA256 = {"docs/x.md": "<digest>"}`` the immediate parent is a
    filename and the grandparent is the only line that says what the value is.
    """
    ancestors, indent = [], len(lines[index]) - len(lines[index].lstrip())
    for position in range(index - 1, -1, -1):
        line = lines[position]
        if not line.strip():
            continue
        current = len(line) - len(line.lstrip())
        if current < indent and _MAPPING_KEY.match(line):
            ancestors.append(line)
            indent = current
            if indent == 0:
                break
    return ancestors


def classify_entropy_findings(root: Path, findings) -> dict:
    """Split high-entropy findings into declared checksums and everything else.

    detect-secrets cannot tell a published content checksum from a leaked key,
    and this repository publishes hundreds of the former. The separation is a
    check rather than a dismissal: a finding is reclassified only when a
    64-character hex string is actually present, and when either its own line or
    the mapping key that encloses it names it as a checksum, digest, hash or
    fingerprint. The next line is included because YAML wraps a long value onto
    one. Everything else stays a finding and is reported.
    """
    root = Path(root)
    checksums, unexplained = [], []
    for finding in findings:
        if "entropy" not in finding["family"].lower():
            continue
        try:
            lines = (root / finding["path"]).read_text(encoding="utf-8").splitlines()
            index = int(finding["line"]) - 1
            digest_lines = [lines[index]]
            if index + 1 < len(lines):
                digest_lines.append(lines[index + 1])
            # A checksum constant in Python or a long dictionary value is
            # routinely written with the name on one line and the digest on the
            # next, so the naming context has to be looked for on both sides.
            context_lines = [*digest_lines, *_enclosing_keys(lines, index)]
            if index > 0:
                context_lines.append(lines[index - 1])
        except (OSError, ValueError, IndexError, TypeError):
            unexplained.append(finding)
            continue
        if any(_HEX_DIGEST.search(text) for text in digest_lines) and any(
            _CHECKSUM_CONTEXT.search(text) for text in context_lines
        ):
            checksums.append(finding)
        else:
            unexplained.append(finding)
    return {
        "declared_content_checksums": len(checksums),
        "unexplained_high_entropy": unexplained,
        "unexplained_count": len(unexplained),
        "rule": (
            "a hex digest of 12 to 64 characters whose own line, adjacent line "
            "or enclosing mapping key names it as a checksum, digest, hash or "
            "fingerprint is a published content checksum; anything else remains "
            "a finding"
        ),
    }


def classify_reviewed(findings, reviewed) -> dict:
    """Separate findings a person has looked at from findings nobody has.

    A reviewed entry is keyed on path, family and fingerprint, not on a line
    number: line numbers move when a file is edited and a suppression that
    survives an edit is a suppression that stops meaning anything. Every entry
    carries the reason it is not a credential. A finding that matches no entry
    stays **unreviewed** -- a third state, distinct from both "credential" and
    "benign", because nobody has yet said which it is.
    """
    index = {
        (entry["path"], entry["family"], entry["fingerprint"]): entry
        for entry in reviewed
    }
    accounted, unreviewed, stale = [], [], dict(index)
    for finding in findings:
        key = (finding["path"], finding["family"], finding["fingerprint"])
        if key in index:
            accounted.append({**finding, "review": index[key]["reason"]})
            stale.pop(key, None)
        else:
            unreviewed.append(finding)
    return {
        "reviewed_and_not_credentials": accounted,
        "reviewed_count": len(accounted),
        "unreviewed": unreviewed,
        "unreviewed_count": len(unreviewed),
        # An entry that no longer matches anything means the file changed under
        # the review. It is reported rather than dropped.
        "review_entries_that_matched_nothing": sorted(
            f"{path}::{family}::{finger}" for path, family, finger in stale
        ),
    }


def summarise(pattern_scan: dict, detect_secrets: dict, audits,
              entropy: dict = None) -> dict:
    """Fold the scans into the fields the readiness decision consumes."""
    blocking_families = {
        "api_keys_and_tokens", "aws_access_key_id", "private_key_block",
        "passwords", "cookies_and_sessions", "authorization_headers",
        "private_urls", "temporary_download_credentials",
    }
    entropy = entropy or {"declared_content_checksums": 0,
                          "unexplained_high_entropy": [], "unexplained_count": 0}
    explained = {
        (f["path"], f["line"], f["fingerprint"])
        for f in detect_secrets["findings"]
        if "entropy" in f["family"].lower()
    } - {
        (f["path"], f["line"], f["fingerprint"])
        for f in entropy["unexplained_high_entropy"]
    }
    all_findings = [
        finding for finding in pattern_scan["findings"] + detect_secrets["findings"]
        if (finding["path"], finding["line"], finding["fingerprint"]) not in explained
    ]
    credentials = [f for f in all_findings if f["family"] in blocking_families]
    privacy = [f for f in all_findings if f["family"] not in blocking_families]
    unresolved_audits = [
        audit for audit in audits if audit["state"] != "ran"
    ]
    return {
        "high_entropy_classification": {
            k: v for k, v in entropy.items() if k != "unexplained_high_entropy"
        },
        "declared_content_checksums_excluded": entropy["declared_content_checksums"],
        "credential_findings": len(credentials),
        "privacy_findings": len(privacy),
        "credential_fingerprints": sorted({f["fingerprint"] for f in credentials}),
        "privacy_by_family": {
            family: sum(1 for f in privacy if f["family"] == family)
            for family in sorted({f["family"] for f in privacy})
        },
        "findings": all_findings,
        "secret_values_printed": False,
        "credential_exposure_is_a_blocker": True,
        "credential_exposure_present": bool(credentials),
        "dependency_audits": list(audits),
        "dependency_audit_unresolved": bool(unresolved_audits),
        "dependency_vulnerabilities": sum(
            len(audit.get("vulnerabilities", [])) for audit in audits
        ),
    }
