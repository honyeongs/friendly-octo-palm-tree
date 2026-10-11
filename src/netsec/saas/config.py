"""Commercial features are opt-in; production never enables developer shortcuts."""

import json
import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ServiceSettings:
    enabled: bool = False
    encryption_key: str = ''
    mail_mode: str = 'local'
    billing_mode: str = 'mock'
    stripe_key: str = ''
    stripe_webhook_secret: str = ''
    prices: dict = field(default_factory=dict)
    launch_confirmed: bool = False
    terms_version: str = 'draft-1'
    terms_url: str = ''
    privacy_url: str = ''
    oidc_issuers: tuple = ()
    webhook_hosts: tuple = ()
    embedded_worker: bool = True
    stale_minutes: int = 15

    def validate(self, secure, backend):
        if not self.enabled:
            return
        if self.mail_mode not in ('local', 'smtp') or self.billing_mode not in ('mock', 'stripe', 'off'):
            raise ValueError('Invalid SaaS delivery/provider mode')
        if not 1 <= self.stale_minutes <= 1440:
            raise ValueError('Invalid stale collection threshold')
        if secure and (not self.encryption_key or self.mail_mode != 'smtp' or self.billing_mode == 'mock'):
            raise ValueError('HTTPS SaaS forbids local mail, mock billing, and missing encryption key')
        if secure and backend != 'postgres':
            raise ValueError('Public SaaS requires PostgreSQL')
        if self.billing_mode == 'stripe' and (not self.stripe_key or not self.stripe_webhook_secret):
            raise ValueError('Stripe keys are required in stripe mode; use off until configured')
        if self.stripe_key.startswith(('sk_live_', 'rk_live_')) and not self.launch_confirmed:
            raise ValueError('Live billing requires explicit release confirmation')
        if secure and not self.launch_confirmed:
            raise ValueError('Public signup requires reviewed terms/privacy and NETSEC_LAUNCH_CONFIRMED=1')
        if secure and (self.terms_version.startswith('draft') or not self.terms_url or not self.privacy_url):
            raise ValueError('Publish reviewed legal documents before public signup')
        for url in (self.terms_url, self.privacy_url):
            if url and (urlsplit(url).scheme != 'https' or not urlsplit(url).hostname or urlsplit(url).username):
                raise ValueError('Published legal documents require HTTPS URLs')
        for issuer in self.oidc_issuers:
            value = urlsplit(issuer)
            if value.scheme != 'https' or not value.hostname or value.username or value.query or value.fragment:
                raise ValueError('OIDC issuers must be operator-approved HTTPS URLs')

    @classmethod
    def from_env(cls):
        return cls(enabled=os.getenv('NETSEC_SAAS_ENABLED') == '1',
                   encryption_key=os.getenv('NETSEC_ENCRYPTION_KEY', ''),
                   mail_mode=os.getenv('NETSEC_MAIL_MODE', 'local'),
                   billing_mode=os.getenv('NETSEC_BILLING_MODE', 'mock'),
                   stripe_key=os.getenv('NETSEC_STRIPE_KEY', ''),
                   stripe_webhook_secret=os.getenv('NETSEC_STRIPE_WEBHOOK_SECRET', ''),
                   prices=json.loads(os.getenv('NETSEC_STRIPE_PRICES', '{}')),
                   launch_confirmed=os.getenv('NETSEC_LAUNCH_CONFIRMED') == '1',
                   terms_version=os.getenv('NETSEC_TERMS_VERSION', 'draft-1'),
                   terms_url=os.getenv('NETSEC_TERMS_URL', ''), privacy_url=os.getenv('NETSEC_PRIVACY_URL', ''),
                   oidc_issuers=tuple(filter(None, os.getenv('NETSEC_OIDC_ISSUERS', '').split(','))),
                   webhook_hosts=tuple(filter(None, os.getenv('NETSEC_WEBHOOK_HOSTS', '').split(','))),
                   embedded_worker=os.getenv('NETSEC_EMBEDDED_WORKER', '1') == '1',
                   stale_minutes=int(os.getenv('NETSEC_STALE_MINUTES', '15')))
