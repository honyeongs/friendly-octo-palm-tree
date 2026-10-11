"""Single-use verification/invite/reset tokens and encrypted delivery queue."""

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from netsec.monitor.accounts import create_organization
from netsec.monitor.database import audit, identifier, now
from netsec.monitor.dependencies import authorize, current_user, same_origin
from netsec.monitor.security import digest, hash_password, rate_limit, token, verify_password
from netsec.saas.plans import check_capacity, provision
from netsec.saas.schemas import Consume, EmailRequest, Invite, Signup

router = APIRouter(prefix='/api/saas')


def available(request: Request):
    if not request.app.state.settings.saas.enabled:
        raise HTTPException(404, 'SaaS 모드가 꺼져 있습니다.')


def reauthenticate(conn, user, password):
    authorize(user, 'admin')
    row = conn.execute('SELECT password_hash FROM users WHERE id=? AND org_id=?', (user['id'], user['org_id'])).fetchone()
    if not row or not verify_password(password, row[0]):
        raise HTTPException(403, '관리자 비밀번호를 다시 확인하세요.')


def sensitive_user(request: Request, user=Depends(current_user)):
    authorize(user, 'admin')
    rate_limit(request.app.state.db, 'reauth:' + user['id'], limit=10, seconds=300)
    return user


def issue(conn, vault, origin, org_id, purpose, email, user_id=None, payload=None):
    raw, stamp = token(), now()
    expiry = (datetime.now(timezone.utc) + timedelta(hours=1 if purpose == 'reset' else 24)).isoformat(timespec='microseconds')
    conn.execute('DELETE FROM action_tokens WHERE org_id=? AND purpose=? AND email=?', (org_id, purpose, email))
    conn.execute('INSERT INTO action_tokens VALUES(?,?,?,?,?,?,?,?)',
                 (digest(raw), org_id, purpose, email, user_id, json.dumps(payload or {}), expiry, stamp))
    body = f'NetSec {purpose}\nWorkspace: {org_id}\n{origin}/#action/{raw}\nExpires: {expiry}'
    conn.execute('INSERT INTO mail_jobs(id,org_id,recipient,encrypted_body,next_at,created_at) VALUES(?,?,?,?,?,?)',
                 (identifier(), org_id, email, vault.seal(org_id, body), stamp, stamp))


@router.post('/signup', dependencies=[Depends(available), Depends(same_origin)], status_code=202)
def signup(payload: Signup, request: Request):
    settings, db = request.app.state.settings, request.app.state.db
    if payload.terms_version != settings.saas.terms_version:
        raise HTTPException(409, '최신 약관 버전을 확인하세요.')
    rate_limit(db, 'signup-ip:' + digest(request.client.host), limit=5, seconds=3600)
    rate_limit(db, 'signup-email:' + digest(payload.email), limit=1, seconds=86400)
    with db.connect(write=True) as conn:
        org_id = create_organization(conn, payload)
        user = conn.execute('SELECT id FROM users WHERE org_id=?', (org_id,)).fetchone()
        conn.execute('UPDATE users SET active=0 WHERE id=?', (user[0],))
        provision(conn, org_id)
        audit(conn, org_id, user[0], 'terms.accept', detail={'version': payload.terms_version})
        issue(conn, request.app.state.vault, settings.origin, org_id, 'verify', payload.email, user[0])
    return {'message': '확인 메일을 보냈습니다. 이메일 확인 후 로그인하세요.'}


@router.post('/email', dependencies=[Depends(available), Depends(same_origin)], status_code=202)
def email_request(payload: EmailRequest, request: Request, purpose: str = 'reset'):
    if purpose not in ('reset', 'verify'):
        raise HTTPException(422, '지원하지 않는 요청입니다.')
    db = request.app.state.db
    rate_limit(db, 'email-ip:' + digest(request.client.host), limit=10, seconds=3600)
    rate_limit(db, 'email-account:' + digest(payload.org_id + payload.email), limit=3, seconds=3600)
    with db.connect(write=True) as conn:
        user = conn.execute('SELECT * FROM users WHERE org_id=? AND email=?', (payload.org_id, payload.email)).fetchone()
        verified = user and conn.execute('SELECT 1 FROM verified_users WHERE user_id=?', (user['id'],)).fetchone()
        if user and ((purpose == 'reset' and user['active']) or (purpose == 'verify' and not verified and not user['active'])):
            issue(conn, request.app.state.vault, request.app.state.settings.origin, payload.org_id, purpose, payload.email, user['id'])
    return {'message': '대상 계정이 있으면 안내 메일을 보냈습니다.'}


@router.post('/consume', dependencies=[Depends(available), Depends(same_origin)])
def consume(payload: Consume, request: Request):
    db = request.app.state.db
    rate_limit(db, 'consume:' + digest(request.client.host), limit=20, seconds=300)
    with db.connect(write=True) as conn:
        row = conn.execute('SELECT * FROM action_tokens WHERE token_hash=? AND expires_at>?', (digest(payload.token), now())).fetchone()
        if not row:
            raise HTTPException(400, '링크가 만료되었거나 이미 사용되었습니다.')
        purpose, org_id, user_id = row['purpose'], row['org_id'], row['user_id']
        if purpose in ('invite', 'reset') and not 12 <= len(payload.password) <= 256:
            raise HTTPException(422, '새 비밀번호는 12자 이상이어야 합니다.')
        if purpose == 'invite':
            if not payload.display_name.strip():
                raise HTTPException(422, '이름을 입력하세요.')
            # Consume the reserved seat before counting; still atomic with user creation.
            conn.execute('DELETE FROM action_tokens WHERE token_hash=?', (digest(payload.token),))
            check_capacity(conn, org_id, 'users')
            if conn.execute('SELECT 1 FROM users WHERE org_id=? AND email=?', (org_id, row['email'])).fetchone():
                raise HTTPException(409, '이미 등록된 계정입니다.')
            user_id = identifier()
            conn.execute('INSERT INTO users(id,org_id,email,display_name,password_hash,role,created_at) VALUES(?,?,?,?,?,?,?)',
                         (user_id, org_id, row['email'], payload.display_name, hash_password(payload.password), json.loads(row['payload'])['role'], now()))
        elif purpose == 'verify':
            conn.execute('UPDATE users SET active=1 WHERE id=? AND org_id=?', (user_id, org_id))
        else:
            live = conn.execute('SELECT active FROM users WHERE id=? AND org_id=?', (user_id, org_id)).fetchone()
            if not live or not live[0]:
                raise HTTPException(400, '유효하지 않은 계정입니다.')
            conn.execute('UPDATE users SET password_hash=? WHERE id=?', (hash_password(payload.password), user_id))
            conn.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
        conn.execute('INSERT INTO verified_users VALUES(?,?) ON CONFLICT(user_id) DO NOTHING', (user_id, now()))
        conn.execute('DELETE FROM action_tokens WHERE token_hash=?', (digest(payload.token),))
        audit(conn, org_id, user_id, 'identity.' + purpose)
    return {'org_id': org_id, 'message': '완료했습니다. 조직 ID와 이메일로 로그인하세요.'}


@router.get('/invites', dependencies=[Depends(available)])
def invites(request: Request, user=Depends(current_user)):
    authorize(user, 'admin')
    with request.app.state.db.connect() as conn:
        rows = conn.execute("SELECT email,payload,expires_at FROM action_tokens WHERE org_id=? AND purpose='invite' AND expires_at>?", (user['org_id'], now())).fetchall()
    return {'items': [{'email': row['email'], 'role': json.loads(row['payload'])['role'], 'expires_at': row['expires_at']} for row in rows]}


@router.post('/invites', dependencies=[Depends(available)], status_code=202)
def invite(payload: Invite, request: Request, user=Depends(current_user)):
    authorize(user, 'admin')
    rate_limit(request.app.state.db, 'invite:' + user['org_id'], limit=20, seconds=3600)
    with request.app.state.db.connect(write=True) as conn:
        if conn.execute('SELECT 1 FROM users WHERE org_id=? AND email=?', (user['org_id'], payload.email)).fetchone():
            raise HTTPException(409, '이미 등록된 계정입니다.')
        conn.execute("DELETE FROM action_tokens WHERE org_id=? AND purpose='invite' AND email=?", (user['org_id'], payload.email))
        check_capacity(conn, user['org_id'], 'users')
        issue(conn, request.app.state.vault, request.app.state.settings.origin, user['org_id'], 'invite', payload.email, payload={'role': payload.role})
        audit(conn, user['org_id'], user['id'], 'user.invite', detail={'role': payload.role})
    return {'ok': True}


@router.get('/dev-mail', dependencies=[Depends(available)])
def dev_mail(request: Request):
    settings = request.app.state.settings
    if settings.secure or settings.saas.mail_mode != 'local' or request.client.host not in ('127.0.0.1', '::1', 'testclient'):
        raise HTTPException(404, '사용할 수 없습니다.')
    with request.app.state.db.connect() as conn:
        rows = conn.execute('SELECT * FROM mail_jobs ORDER BY created_at DESC LIMIT 10').fetchall()
    return {'items': [{'recipient': row['recipient'], 'body': request.app.state.vault.open(row['org_id'], row['encrypted_body'])} for row in rows]}


@router.delete('/invites', dependencies=[Depends(available)])
def cancel_invite(payload: Invite, request: Request, user=Depends(current_user)):
    authorize(user, 'admin')
    with request.app.state.db.connect(write=True) as conn:
        conn.execute("DELETE FROM action_tokens WHERE org_id=? AND email=? AND purpose='invite'", (user['org_id'], payload.email))
        audit(conn, user['org_id'], user['id'], 'user.invite_cancel')
    return {'ok': True}
