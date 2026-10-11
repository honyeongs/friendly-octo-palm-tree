"""Authorization-code SSO via Authlib, server-side state and PKCE."""

import hmac
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from netsec.monitor.database import audit, now
from netsec.monitor.dependencies import COOKIE
from netsec.monitor.security import digest, rate_limit, token
from netsec.saas.identity import available
from netsec.saas.network import destination
from netsec.saas.secrets import integration

router = APIRouter(prefix='/api/saas/sso', dependencies=[Depends(available)])


def remote(settings, value):
    from authlib.integrations.starlette_client import OAuth
    issuer = value['oidc_issuer']
    if issuer not in settings.saas.oidc_issuers:
        raise HTTPException(403, '승인되지 않은 발급자입니다.')
    # Issuer URLs are operator-controlled, never accepted directly from login input.
    destination(issuer, [urlsplit(issuer).hostname])
    oauth = OAuth()
    return oauth.register('company', client_id=value['oidc_client_id'], client_secret=value.get('oidc_client_secret', ''),
                          server_metadata_url=issuer.rstrip('/') + '/.well-known/openid-configuration',
                          client_kwargs={'scope': 'openid email profile', 'code_challenge_method': 'S256', 'timeout': 10, 'trust_env': False})


@router.get('/start')
async def start(request: Request, org_id: str):
    db, settings = request.app.state.db, request.app.state.settings
    if len(org_id) > 64:
        raise HTTPException(422, '유효하지 않은 조직입니다.')
    rate_limit(db, 'sso-start:' + digest(request.client.host), limit=20, seconds=300)
    with db.connect() as conn:
        value = integration(conn, request.app.state.vault, org_id)
    if not value.get('oidc_issuer'):
        raise HTTPException(404, 'SSO가 설정되지 않았습니다.')
    client = remote(settings, value)
    browser, nonce, verifier = token(), token(), token() + token()
    params = await client.create_authorization_url(settings.origin + '/api/saas/sso/callback', nonce=nonce, code_verifier=verifier)
    if urlsplit(params['url']).scheme != 'https':
        raise HTTPException(502, '인증 제공자의 주소가 안전하지 않습니다.')
    expiry = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(timespec='microseconds')
    with db.connect(write=True) as conn:
        conn.execute('DELETE FROM oidc_transactions WHERE expires_at<=?', (now(),))
        conn.execute('INSERT INTO oidc_transactions VALUES(?,?,?,?,?)', (digest(params['state']), org_id, digest(browser),
                     request.app.state.vault.seal(org_id, {'nonce': nonce, 'code_verifier': verifier, 'issuer': value['oidc_issuer']}), expiry))
    response = RedirectResponse(params['url'], status_code=303)
    response.set_cookie('netsec_oidc', browser, max_age=600, httponly=True, secure=settings.secure, samesite='lax', path='/api/saas/sso')
    return response


@router.get('/callback')
async def callback(request: Request, state: str = '', code: str = ''):
    db, settings = request.app.state.db, request.app.state.settings
    if not state or len(state) > 200 or not code or len(code) > 4000:
        raise HTTPException(400, 'SSO 응답이 올바르지 않습니다.')
    with db.connect(write=True) as conn:
        row = conn.execute('SELECT * FROM oidc_transactions WHERE state_hash=? AND expires_at>?', (digest(state), now())).fetchone()
        if not row or not hmac.compare_digest(row['browser_hash'], digest(request.cookies.get('netsec_oidc', ''))):
            raise HTTPException(400, 'SSO 요청이 만료되었거나 브라우저가 일치하지 않습니다.')
        conn.execute('DELETE FROM oidc_transactions WHERE state_hash=?', (digest(state),))
        org_id = row['org_id']
        params = request.app.state.vault.open(org_id, row['encrypted_params'])
        value = integration(conn, request.app.state.vault, org_id)
    if params['issuer'] != value.get('oidc_issuer'):
        raise HTTPException(400, 'SSO 설정이 변경되었습니다.')
    try:
        client = remote(settings, value)
        result = await client.fetch_access_token(code=code, code_verifier=params['code_verifier'], redirect_uri=settings.origin + '/api/saas/sso/callback')
        claims = await client.parse_id_token(result, nonce=params['nonce'], claims_options={'iss': {'essential': True, 'value': value['oidc_issuer']}})
        if (claims.get('iss') != params['issuer'] or claims.get('nonce') != params['nonce']
                or claims.get('email_verified') is not True or not claims.get('sub') or not claims.get('email')):
            raise ValueError('Verified identity required')
        methods = set(claims.get('amr', []))
        if value.get('oidc_require_mfa', True) and not ('mfa' in methods or ('pwd' in methods and methods & {'otp', 'hwk', 'swk'})):
            raise ValueError('MFA evidence required')
    except Exception:
        raise HTTPException(403, 'SSO 검증에 실패했습니다. 발급자·대상·MFA 정책을 확인하세요.') from None
    with db.connect(write=True) as conn:
        binding = conn.execute('SELECT user_id FROM oidc_bindings WHERE org_id=? AND issuer=? AND subject=?', (org_id, value['oidc_issuer'], claims['sub'])).fetchone()
        if binding:
            user = conn.execute('SELECT * FROM users WHERE org_id=? AND id=? AND active=1', (org_id, binding[0])).fetchone()
        else:
            # Never provision an account solely from a matching email domain.
            user = conn.execute('SELECT u.* FROM users u JOIN verified_users v ON u.id=v.user_id WHERE u.org_id=? AND u.email=? AND u.active=1', (org_id, claims['email'].lower())).fetchone()
            if user and conn.execute('SELECT 1 FROM oidc_bindings WHERE org_id=? AND issuer=? AND user_id=?', (org_id, value['oidc_issuer'], user['id'])).fetchone():
                user = None
            if user:
                conn.execute('INSERT INTO oidc_bindings VALUES(?,?,?,?)', (org_id, value['oidc_issuer'], claims['sub'], user['id']))
        if not user:
            raise HTTPException(403, '초대·이메일 확인을 마친 활성 계정이 필요합니다.')
        raw, csrf = token(), token()
        expiry = (datetime.now(timezone.utc) + timedelta(hours=settings.session_hours)).isoformat(timespec='microseconds')
        conn.execute('INSERT INTO sessions VALUES(?,?,?,?)', (digest(raw), user['id'], csrf, expiry))
        audit(conn, org_id, user['id'], 'sso.login')
    response = RedirectResponse(settings.origin + '/', status_code=303)
    response.delete_cookie('netsec_oidc', path='/api/saas/sso')
    response.set_cookie(COOKIE, raw, max_age=settings.session_hours * 3600, httponly=True, secure=settings.secure, samesite='strict', path='/')
    return response
