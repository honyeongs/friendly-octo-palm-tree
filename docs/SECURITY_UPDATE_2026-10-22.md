# certifi Security Update

Verification date: 2026-10-22 (Asia/Seoul).

## Finding and Scope

- Advisory: [GHSA-6q48-6c7w-9gw2](https://github.com/advisories/GHSA-6q48-6c7w-9gw2), alias `PYSEC-2026-4320`, published 2026-10-20.
- The previous local SaaS lock contained `certifi==2026.7.22`. The advisory describes compromised intermediate CA keys chaining to an emSign root, enabling TLS interception by an on-path attacker under the stated conditions. No exploitation was established by this review.
- Updated to the advisory's fixed release, [certifi 2026.10.19](https://github.com/certifi/python-certifi/releases/tag/2026.10.19). The other 30 runtime pins are unchanged.
- The three public browser-local PWAs do not bundle certifi or the SaaS HTTP integrations. They do not require redeployment for this dependency update. This statement is not an audit of every component in those websites or their hosting platform.

## Changes

- Regenerated `requirements-runtime.lock`, `DEPENDENCIES.json` and `SBOM.cdx.json` using `scripts/supply_chain.py` in an environment matching all existing pins except the approved certifi upgrade.
- Retained certifi's original MPL-2.0 notice unchanged. All 35 upstream notice files match their recorded SHA-256 values.
- Restored exact installed upstream bytes for three existing notices (charset-normalizer, psycopg-binary, pydantic-core). Their prior Git blobs used LF while the inventory recorded the upstream CRLF bytes. Only line endings changed; license terms and checksums were not rewritten.
- Added four regression checks for lock/inventory equality, SBOM package URLs, original notice hashes and the certifi security minimum. No vulnerability suppression or TLS verification bypass was added.
- Preserved older verification documents as historical evidence and linked them to this update.

## Observed Verification

- `pip-audit 2.10.1`: all 31 pinned runtime packages queried, zero skipped packages, zero known vulnerabilities at this verification time. Full audit JSON is retained by the CI security artifact; this is not a future or whole-system safety guarantee.
- `pip check`: no broken requirements.
- `bandit 1.9.4`: high-severity/high-confidence gate passed. Complete severity totals remain high 0, medium 15, low 4; existing warnings and their interpretation are documented in `SECURITY_REVIEW.md`.
- Full Windows/Python 3.14.7 regression: 162 tests, 143 passed, 19 skipped, zero failures/errors. Eighteen require the dedicated PostgreSQL service and one requires Windows link privileges; these skips are not counted as passes.
- Representative scenarios: 10/10 passed, overlapping the full suite rather than additional independent samples.
- SaaS browser workflow passed: signup, local email verification, login, trial, mock billing, invitation, source ingestion, detection, deadline, health, encrypted integration, privacy export and desktop/360px/390px layouts. External identity, email and payment providers were not contacted.
- The first local attempt hit sandbox temporary-directory permission errors. Using an explicitly writable workspace temporary directory resolved these without product-code changes; only the successful sanitized rerun is published.
- Public machine-readable evidence and skip categories: [JSON](testing/2026-10-22-certifi-update.json), [readable record](testing/2026-10-22-certifi-update.md). No raw logs, accounts, private paths, credentials, tokens or exception messages are included.
- GitHub validation for the delivered commit is available under [Actions](https://github.com/honyeongs/friendly-octo-palm-tree/actions). Each push reruns dependency audit, static analysis, Windows/Linux tests, browser tests, PostgreSQL, the SSH lab, container checks and PWA checks. Consult the run's exact commit and conclusion rather than treating this link as a claim of success.

## Existing Deployments

Updating Git does not patch an already installed environment or a running container automatically. In that deployment's virtual environment, install the updated lock, check dependencies and restart the application and workers:

```sh
python -m pip install -r requirements-runtime.lock
python -m pip check
```

Rebuild and roll out container images from the patched commit when applicable. Do not disable certificate verification as a workaround. No external API keys are needed for this patch or its local tests.

## Limits

This is a targeted dependency remediation, not a penetration test, proof of absence of compromise, malware verdict, legal opinion or certification. The application is not claiming that all listed warnings are eliminated. Existing operating-system, hosting, key-management, third-party integration and legal review requirements still apply. Original third-party terms remain in `third_party/` and `THIRD_PARTY_NOTICES.md`; preserving them does not guarantee compliance for every downstream deployment.
