"""Explicit scope and provenance for ten independent feature scenarios."""
PROJECT = {
    "cases": [
        [
            "SSH CLI sample and independent expected summary",
            "tests.test_cli.CliTests.test_sample_matches_independent_expected_summary"
        ],
        [
            "Native journal microsecond timestamp",
            "tests.test_journal.JournalTests.test_native_microseconds_preserved"
        ],
        [
            "Failure burst followed by matching success",
            "tests.test_success_after_failures.SuccessCorrelationTests.test_matching_user_and_burst"
        ],
        [
            "PCAP and PCAPNG transport parity",
            "tests.test_packets.PacketTests.test_pcap_and_pcapng_have_same_transport_counts"
        ],
        [
            "Event ingestion and idempotent deduplication",
            "tests.test_monitor.MonitorTests.test_ingestion_detects_and_deduplicates"
        ],
        [
            "Tenant isolation for reads and mutations",
            "tests.test_monitor.MonitorTests.test_isolation_lists_details_mutations_and_assignees"
        ],
        [
            "CSRF token and Origin enforcement",
            "tests.test_monitor.MonitorTests.test_csrf_and_origin"
        ],
        [
            "Atomic SaaS quota, replay and conflict",
            "tests.test_saas.SaasTests.test_quota_atomic_replay_and_conflict"
        ],
        [
            "Encrypted tenant-bound integration secrets",
            "tests.test_saas.SaasTests.test_integrations_encrypt_bound_secrets_and_redact"
        ],
        [
            "OIDC signature, issuer, audience, expiry and nonce",
            "tests.test_oidc_crypto.OidcCryptoTests.test_signature_issuer_audience_expiration_nonce"
        ]
    ],
    "checks": [
        [
            "web-data",
            [
                "--test",
                "tests/web/data.test.mjs"
            ]
        ],
        [
            "comparison-browser",
            [
                "tests/browser/smoke.mjs"
            ]
        ],
        [
            "monitor-browser",
            [
                "tests/browser/monitor.mjs"
            ]
        ],
        [
            "saas-browser",
            [
                "tests/browser/saas.mjs"
            ]
        ]
    ],
    "limitations": [
        "Local authentication/tenant tests use isolated temporary SQLite databases and synthetic events.",
        "Packet inputs are repository lab fixtures; this run does not capture the user's network.",
        "PostgreSQL contracts are skipped locally unless --allow-postgres explicitly targets a dedicated test server.",
        "Real SMTP, SSO providers, payment charging, Docker and a live Linux SSH lab are not exercised by this local run."
    ]
}

