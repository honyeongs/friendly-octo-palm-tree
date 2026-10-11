"""Standalone-capable mail and tenant notification workers."""

import json
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from netsec.monitor.database import now
from netsec.saas.network import post_json
from netsec.saas.secrets import integration


def send_mail(settings, recipient, subject, body, message_id):
    message = EmailMessage()
    message['From'], message['To'], message['Subject'] = settings.smtp_from, recipient, subject
    message['Message-ID'] = f'<{message_id}@netsec.local>'
    message.set_content(body)
    context = ssl.create_default_context()
    factory = smtplib.SMTP_SSL if settings.smtp_tls == 'ssl' else smtplib.SMTP
    with factory(settings.smtp_host, settings.smtp_port, timeout=10, **({'context': context} if settings.smtp_tls == 'ssl' else {})) as smtp:
        if settings.smtp_tls == 'starttls':
            smtp.starttls(context=context)
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)


def dispatch_mail(db, settings, vault):
    if settings.saas.mail_mode == 'local':
        return False
    with db.connect(write=True) as conn:
        stamp = now()
        row = conn.execute("SELECT * FROM mail_jobs WHERE (status='pending' AND next_at<=?) OR (status='processing' AND lease_until<=?) ORDER BY created_at LIMIT 1", (stamp, stamp)).fetchone()
        if not row:
            return False
        lease = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat(timespec='microseconds')
        conn.execute("UPDATE mail_jobs SET status='processing',attempts=attempts+1,lease_until=? WHERE id=?", (lease, row['id']))
    try:
        send_mail(settings, row['recipient'], '[NetSec] Account action', vault.open(row['org_id'], row['encrypted_body']), row['id'])
        status = 'sent'
    except Exception:
        status = 'failed' if row['attempts'] + 1 >= 5 else 'pending'
    next_at = (datetime.now(timezone.utc) + timedelta(seconds=min(3600, 30 * 2 ** row['attempts']))).isoformat(timespec='microseconds')
    with db.connect(write=True) as conn:
        conn.execute('UPDATE mail_jobs SET status=?,next_at=?,lease_until=NULL WHERE id=? AND lease_until=?', (status, next_at, row['id'], lease))
    return True


def tenant_deliver(db, settings, vault, channel, org, incident, delivery_id):
    if channel == 'in_app':
        return 'sent'
    payload = {'delivery_id': delivery_id, 'organization_id': org['id'], 'incident_id': incident['id'],
               'rule': incident['rule'], 'severity': incident['severity'], 'title': incident['title'],
               'url': settings.origin + '/#incidents/' + incident['id']}
    if channel == 'email':
        if not settings.smtp_host or not settings.smtp_from or not org['notification_email']:
            return 'skipped'
        with db.connect() as conn:
            verified = conn.execute('SELECT 1 FROM users u JOIN verified_users v ON u.id=v.user_id WHERE u.org_id=? AND u.email=? AND u.active=1', (org['id'], org['notification_email'])).fetchone()
        if not verified:
            return 'skipped'
        send_mail(settings, org['notification_email'], '[NetSec] ' + incident['title'], json.dumps(payload, ensure_ascii=False), delivery_id)
    elif channel == 'webhook':
        if not org['webhook_enabled']:
            return 'skipped'
        with db.connect() as conn:
            value = integration(conn, vault, org['id'])
        if not value.get('webhook_url'):
            return 'skipped'
        headers = {'Idempotency-Key': delivery_id}
        if value.get('webhook_token'):
            headers['Authorization'] = 'Bearer ' + value['webhook_token']
        post_json(value['webhook_url'], settings.saas.webhook_hosts, payload, headers)
    return 'sent'
