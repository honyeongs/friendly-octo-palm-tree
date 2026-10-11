"""Authenticated tenant-bound encryption; secret values never appear in read APIs."""

import json
import os
from pathlib import Path


class Vault:
    def __init__(self, settings, db):
        from cryptography.fernet import Fernet
        key = settings.saas.encryption_key
        if not key:
            if settings.secure or db.backend != 'sqlite':
                raise ValueError('An external encryption key is required')
            path = db.path.parent / '.netsec-key'
            try:
                with path.open('xb') as stream:
                    os.chmod(path, 0o600)
                    stream.write(Fernet.generate_key())
            except FileExistsError:
                pass
            key = path.read_bytes()
        self.fernet = Fernet(key.encode() if isinstance(key, str) else key)

    def seal(self, org_id, value):
        return self.fernet.encrypt(json.dumps({'tenant': org_id, 'value': value}).encode()).decode()

    def open(self, org_id, encrypted):
        payload = json.loads(self.fernet.decrypt(encrypted.encode()))
        if payload['tenant'] != org_id:
            raise ValueError('Secret tenant mismatch')
        return payload['value']


def integration(conn, vault, org_id):
    row = conn.execute('SELECT encrypted_config FROM tenant_integrations WHERE org_id=?', (org_id,)).fetchone()
    return vault.open(org_id, row[0]) if row else {}
