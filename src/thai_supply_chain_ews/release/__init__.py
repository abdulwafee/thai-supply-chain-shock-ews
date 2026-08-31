"""Release preparation (Task E2).

Builds a public-release allowlist from the filesystem, verifies a clean release
tree installs and tests on its own, audits built package contents, and wraps the
secret and dependency scans.

Publishes nothing. No commit, tag, push or upload, and no locked outcome is ever
opened, hashed, scanned or copied.
"""
