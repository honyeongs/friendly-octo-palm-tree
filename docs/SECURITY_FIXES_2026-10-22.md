# Security Fix Verification

Date: 2026-10-22 (Asia/Seoul). Repository: `friendly-octo-palm-tree`.

## Deployed Result

- URL: [public website](https://netsec-lab-web.yao0422q.chatgpt.site/). Existing Site identity, URL and public audience were preserved.
- Successful deployment: `appgdep_6ad9559c0820819195bc51300ae462bf`.
- Saved version: `appgprj_6ad93877c38481918b30365f73997cc2~appgver_5e16184e3508819182244affc35e22c7`.
- Sites source commit: `676bde4d3b6709204e7c4e0efe354d90b7ef50c0`. This is separate from the GitHub source repository commit.
- The deployment is a small read-only public-asset Worker rather than the former static route. It does not accept analysis uploads, persist user input, proxy arbitrary destinations or add an authentication/billing backend.
- Confirmed actual document, engine-worker script and 404 responses contain CSP, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`. CSP includes `frame-ancestors 'none'` and limits Worker connections to the same origin.
- App code and the unchanged licensed runtime are gzip-packaged with their original notice files. No selected user file or original device log is packaged.
- Explicit `encodeBody: manual` prevents the hosting runtime from recompressing precompressed bytes. An intermediate NetSec rollout exposed this hosting-specific issue despite local tests passing. It was corrected in the successful deployment above and a regression check was added. Do not treat that intermediate rollout as validated.

## SaaS Authentication and Error Responses

- SSO requests now carry an encrypted configuration-revision binding. The revision is derived from the saved authenticated-encryption envelope, which changes even when settings are changed and restored.
- The start route checks the revision again before saving the transaction. The callback checks it before exchanging credentials and, within the same write transaction as binding/session creation, after awaiting the provider. Disabling or changing SSO cannot be undone by a stale in-flight callback.
- Pre-update transactions without a revision fail closed. They must be restarted; there is no database schema migration.
- Early invalid-proxy, unsupported-encoding and oversized-body responses now use the same security-header sender as normal routed responses.
- Five new SSO contracts cover in-flight disable, change-and-restore, discovery-time change, legacy transactions and normal single-use login. SQLite runs locally; the dedicated PostgreSQL CI job also runs those five contracts.
- Local adversarial verification uses synthetic accounts and mocked IdP responses. Separate existing Authlib tests cover real cryptographic signature and claim checks; no external IdP was contacted.
- SaaS browser signup, mail verification, login, mock billing, ingestion, incident operations, encrypted settings, privacy export and mobile workflows passed. Live SMTP/IdP/payment processing remains outside this validation.
- Runtime lock: certifi remains at the patched 2026.10.19 release; no dependency pins were changed for these code fixes.

## Verification Performed

- Full local regression: 178 tests, 154 passed, 24 skipped, zero failures/errors. Skips: 23 dedicated PostgreSQL contracts and one Windows file-link privilege check; not counted as passes.
- The pinned 31-package runtime audit returned zero known vulnerabilities at this check. Bandit high-severity/high-confidence gate passed; existing totals remain high 0, medium 15, low 4. These warnings were not suppressed or claimed eliminated.

- Five Python packaging checks passed: fixed public allowlist/original bytes, checksum mismatch rejection, directory-escape rejection, input/output separation and preservation/rejection of unrelated output files.
- Five Node Worker checks passed: security headers, gzip round-trip, explicit manual encoding, bodyless HEAD/method rejection, and fixed asset paths.
- Local browser checks and a fresh unauthenticated Chromium context at the actual public URL each passed all 12 checks: actual document/Worker/error headers; blocked cross-origin framing; browser-local analysis; native Python parity/input boundaries; cancellation/recovery; manifest/icons; Windows shortcut download; desktop/390px/360px layouts; install control; offline reload/analysis; session reset; no input transmission/external app requests/page errors.
- The browser checks verify analysis still works with the Worker response CSP enforced, not only with an HTML meta policy.
- The former ten representative portfolio cases passed again. They overlap the full suite and are not extra independent samples.
- Sanitized full local test evidence: [JSON](testing/2026-10-22-security-fixes.json), [readable record](testing/2026-10-22-security-fixes.md). Test IDs, results, counts, durations, source fingerprints and categorized skips only; no raw telemetry, exception messages, personal paths, accounts, tokens or screenshots.
- Each GitHub push independently reruns the configured CI jobs. Check the [Actions run](https://github.com/honyeongs/friendly-octo-palm-tree/actions) for the exact commit and conclusion; a local pass is not a remote CI pass.

## Reproduction and Operational Notes

See [website build instructions](WEBSITE.md). Run `python tools/build_website.py` with the reviewed runtime archive, then `python tools/build_hosting.py`, the Python/Node checks and `node tests/browser/website.mjs`. Set `SITE_URL` to the actual public URL for a post-deployment run.

The Service Worker cache version changed so previously installed apps replace older public assets. Open or reload the app once while online to receive the update. Actual Windows installation still requires the browser's user confirmation.

No external API keys are needed. Separately running SaaS/container installations must update their own checkout/image and restart; a GitHub push does not update a separate running process.

## Limits

This is targeted remediation and regression verification, not a full penetration test, hosting/OS/WASM CVE inventory, malware verdict, proof of absence of compromise or security certification. Existing local development servers remain loopback-only and must not be exposed publicly. Synthetic tests do not establish real-device detection/false-positive rates. Original third-party notices and terms remain applicable; this change is not legal advice or a licensing guarantee.
