"""Tenant-scoped encrypted notification/SSO settings, with redacted reads."""

from fastapi import APIRouter, Depends, HTTPException, Request

from netsec.monitor.database import audit, now
from netsec.monitor.dependencies import authorize, current_user
from netsec.monitor.security import rate_limit
from netsec.saas.identity import available, reauthenticate, sensitive_user
from netsec.saas.network import destination
from netsec.saas.schemas import Integration
from netsec.saas.secrets import integration

router = APIRouter(prefix='/api/saas', dependencies=[Depends(available)])


@router.get('/integrations')
def get_integrations(request: Request, user=Depends(current_user)):
    authorize(user, 'admin')
    with request.app.state.db.connect() as conn:
        value = integration(conn, request.app.state.vault, user['org_id'])
    return {'webhook_url': value.get('webhook_url', ''), 'webhook_token_set': bool(value.get('webhook_token')),
            'oidc_issuer': value.get('oidc_issuer', ''), 'oidc_client_id': value.get('oidc_client_id', ''),
            'oidc_client_secret_set': bool(value.get('oidc_client_secret')), 'oidc_require_mfa': value.get('oidc_require_mfa', True),
            'sso_required': value.get('sso_required', False), 'approved_issuers': request.app.state.settings.saas.oidc_issuers}


@router.put('/integrations')
def update_integrations(payload: Integration, request: Request, user=Depends(sensitive_user)):
    settings, db = request.app.state.settings, request.app.state.db
    rate_limit(db, 'integrations:' + user['id'], limit=5, seconds=300)
    if payload.oidc_issuer and payload.oidc_issuer not in settings.saas.oidc_issuers:
        raise HTTPException(422, '운영자가 승인한 OIDC 발급자만 사용할 수 있습니다.')
    if payload.webhook_url:
        try:
            destination(payload.webhook_url, settings.saas.webhook_hosts)
        except (ValueError, OSError):
            raise HTTPException(422, '승인된 공개 HTTPS 웹훅 주소가 필요합니다.') from None
    if payload.sso_required and not payload.oidc_issuer:
        raise HTTPException(422, 'SSO 필수 모드에는 발급자가 필요합니다.')
    with db.connect(write=True) as conn:
        reauthenticate(conn, user, payload.password)
        value = integration(conn, request.app.state.vault, user['org_id'])
        # To avoid lockout, mandatory SSO requires a successful binding for this administrator.
        if payload.sso_required and not conn.execute('SELECT 1 FROM oidc_bindings WHERE org_id=? AND user_id=? AND issuer=?', (user['org_id'], user['id'], payload.oidc_issuer)).fetchone():
            raise HTTPException(409, '먼저 이 관리자 계정으로 SSO 로그인을 검증하세요.')
        new = payload.model_dump(exclude={'password'})
        for key in ('webhook_token', 'oidc_client_secret'):
            if new[key] is None:
                new[key] = value.get(key, '')
        if new['oidc_issuer'] and not new['oidc_client_id']:
            raise HTTPException(422, 'OIDC 클라이언트 ID가 필요합니다.')
        conn.execute('INSERT INTO tenant_integrations VALUES(?,?,?) ON CONFLICT(org_id) DO UPDATE SET encrypted_config=excluded.encrypted_config,updated_at=excluded.updated_at',
                     (user['org_id'], request.app.state.vault.seal(user['org_id'], new), now()))
        conn.execute('DELETE FROM oidc_transactions WHERE org_id=?', (user['org_id'],))
        if new['sso_required'] or new['oidc_issuer'] != value.get('oidc_issuer', ''):
            conn.execute('DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE org_id=?)', (user['org_id'],))
        audit(conn, user['org_id'], user['id'], 'integrations.update', detail={'webhook_enabled': bool(new['webhook_url']), 'sso_required': new['sso_required']})
    return {'ok': True}
