"""Collection health, response deadlines and customer privacy workflows."""

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from netsec.monitor.database import audit, identifier, now
from netsec.monitor.dependencies import authorize, current_user, scoped
from netsec.saas.identity import available, reauthenticate, sensitive_user
from netsec.saas.schemas import Due, PrivacyRequest

router = APIRouter(prefix='/api/saas', dependencies=[Depends(available)])


@router.get('/health')
def health(request: Request, user=Depends(current_user)):
    with request.app.state.db.connect() as conn:
        rows = conn.execute('SELECT id,name,last_seen,created_at FROM sources WHERE org_id=? AND active=1', (user['org_id'],)).fetchall()
        alerts = conn.execute("SELECT id,kind,title,status,created_at FROM service_alerts WHERE org_id=? AND status='open' ORDER BY created_at DESC LIMIT 100", (user['org_id'],)).fetchall()
        queue = conn.execute("SELECT count(*) count,min(created_at) oldest FROM outbox WHERE org_id=? AND status IN ('pending','processing')", (user['org_id'],)).fetchone()
        tasks = conn.execute("SELECT t.*,i.title,i.status FROM incident_tasks t JOIN incidents i ON i.id=t.incident_id WHERE t.org_id=? AND i.status IN ('open','investigating') ORDER BY t.due_at LIMIT 100", (user['org_id'],)).fetchall()
        heartbeat = conn.execute('SELECT max(updated_at) FROM worker_heartbeats').fetchone()[0]
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=request.app.state.settings.saas.stale_minutes)).isoformat(timespec='microseconds')
    return {'items': [{**dict(row), 'status': 'stale' if (row['last_seen'] or row['created_at']) < cutoff else 'healthy'} for row in rows],
            'alerts': [dict(row) for row in alerts], 'queue': dict(queue), 'tasks': [dict(row) for row in tasks],
            'worker_alive': bool(heartbeat and heartbeat > (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat(timespec='microseconds'))}


@router.put('/incidents/{item_id}/task')
def task(item_id: str, payload: Due, request: Request, user=Depends(current_user)):
    authorize(user, 'admin', 'analyst')
    clock = datetime.now(timezone.utc)
    if not clock - timedelta(minutes=1) <= payload.due_at <= clock + timedelta(days=90):
        raise HTTPException(422, '처리 기한은 현재부터 90일 이내여야 합니다.')
    with request.app.state.db.connect(write=True) as conn:
        incident = scoped(conn, 'incidents', user['org_id'], item_id)
        if incident['version'] != payload.version:
            raise HTTPException(409, '사건이 변경되었습니다. 다시 확인하세요.')
        due = payload.due_at.isoformat(timespec='microseconds')
        conn.execute('INSERT INTO incident_tasks(incident_id,org_id,due_at,next_reminder,ticket_ref) VALUES(?,?,?,?,?) ON CONFLICT(incident_id) DO UPDATE SET due_at=excluded.due_at,next_reminder=excluded.next_reminder,ticket_ref=excluded.ticket_ref,reminders=0',
                     (item_id, user['org_id'], due, due, payload.ticket_ref))
        conn.execute('UPDATE incidents SET version=version+1,updated_at=? WHERE id=?', (now(), item_id))
        audit(conn, user['org_id'], user['id'], 'incident.deadline', item_id, {'due_at': due})
    return {'ok': True}


@router.get('/privacy')
def privacy(request: Request, user=Depends(current_user)):
    authorize(user, 'admin')
    with request.app.state.db.connect() as conn:
        rows = conn.execute('SELECT id,kind,status,created_at,resolved_at FROM privacy_requests WHERE org_id=? ORDER BY created_at DESC LIMIT 100', (user['org_id'],)).fetchall()
    return {'items': [dict(row) for row in rows]}


@router.post('/privacy', status_code=202)
def privacy_request(payload: PrivacyRequest, request: Request, user=Depends(sensitive_user)):
    with request.app.state.db.connect(write=True) as conn:
        reauthenticate(conn, user, payload.password)
        if conn.execute("SELECT 1 FROM privacy_requests WHERE org_id=? AND kind=? AND status='pending'", (user['org_id'], payload.kind)).fetchone():
            raise HTTPException(409, '이미 접수된 요청입니다.')
        item_id = identifier()
        conn.execute('INSERT INTO privacy_requests(id,org_id,user_id,kind,created_at) VALUES(?,?,?,?,?)', (item_id, user['org_id'], user['id'], payload.kind, now()))
        audit(conn, user['org_id'], user['id'], 'privacy.request', item_id, {'kind': payload.kind})
    return {'id': item_id, 'status': 'pending', 'message': '운영자 검토 대상으로 접수했습니다. 즉시 삭제된 것은 아닙니다.'}


@router.post('/privacy/export')
def privacy_export(payload: PrivacyRequest, request: Request, user=Depends(sensitive_user)):
    if payload.kind != 'export':
        raise HTTPException(422, '내보내기 요청이 필요합니다.')
    with request.app.state.db.connect(write=True) as conn:
        reauthenticate(conn, user, payload.password)
        result = {}
        fields = {'users': 'id,email,display_name,role,active,created_at', 'sources': 'id,name,kind,active,created_at,last_seen',
                  'events': 'event_id,source_id,timestamp,event_type,outcome,source_ip,username,host,method',
                  'incidents': 'id,source_id,rule,severity,title,status,first_seen,last_seen,evidence_json',
                  'comments': 'id,incident_id,author_id,body,created_at', 'audit': 'action,actor_id,target_id,detail,created_at'}
        truncated = []
        for table, columns in fields.items():
            rows = conn.execute(f'SELECT {columns} FROM {table} WHERE org_id=? LIMIT 10001', (user['org_id'],)).fetchall()
            result[table] = [dict(row) for row in rows[:10000]]
            if len(rows) > 10000:
                truncated.append(table)
        audit(conn, user['org_id'], user['id'], 'privacy.export', detail={'truncated': truncated})
    return {'org_id': user['org_id'], 'exported_at': now(), 'truncated_tables': truncated, 'data': result}


def housekeeping(db, settings):
    clock = datetime.now(timezone.utc)
    cutoff = (clock - timedelta(minutes=settings.saas.stale_minutes)).isoformat(timespec='microseconds')
    with db.connect(write=True) as conn:
        conn.execute('DELETE FROM action_tokens WHERE expires_at<=?', (now(),))
        conn.execute('DELETE FROM oidc_transactions WHERE expires_at<=?', (now(),))
        sources = conn.execute('SELECT id,org_id,name,last_seen,created_at FROM sources WHERE active=1').fetchall()
        for source in sources:
            key, stamp = 'stale:' + source['id'], now()
            if (source['last_seen'] or source['created_at']) < cutoff:
                conn.execute("INSERT INTO service_alerts(id,org_id,alert_key,kind,title,created_at,updated_at) VALUES(?,?,?,'collection','수집이 중단된 소스가 있습니다.',?,?) ON CONFLICT(org_id,alert_key) DO UPDATE SET status='open',updated_at=excluded.updated_at",
                             (identifier(), source['org_id'], key, stamp, stamp))
            else:
                conn.execute("UPDATE service_alerts SET status='resolved',updated_at=? WHERE org_id=? AND alert_key=?", (stamp, source['org_id'], key))
        tasks = conn.execute("SELECT t.* FROM incident_tasks t JOIN incidents i ON i.id=t.incident_id WHERE i.status IN ('open','investigating') AND t.next_reminder<=? AND t.reminders<10", (now(),)).fetchall()
        for task in tasks:
            stamp = now()
            conn.execute("INSERT INTO service_alerts(id,org_id,alert_key,kind,title,created_at,updated_at) VALUES(?,?,?,'deadline','처리 기한을 넘긴 사건이 있습니다.',?,?) ON CONFLICT(org_id,alert_key) DO UPDATE SET status='open',updated_at=excluded.updated_at",
                         (identifier(), task['org_id'], 'due:' + task['incident_id'], stamp, stamp))
            # Fresh delivery IDs distinguish reminders from retries of the original notification.
            for channel in ('in_app', 'email', 'webhook'):
                conn.execute("UPDATE outbox SET id=?,status='pending',attempts=0,next_at=?,lease_until=NULL,error='' WHERE incident_id=? AND channel=? AND status NOT IN ('processing','pending')",
                             (identifier(), stamp, task['incident_id'], channel))
            next_at = (clock + timedelta(hours=4)).isoformat(timespec='microseconds')
            conn.execute('UPDATE incident_tasks SET reminders=reminders+1,next_reminder=? WHERE incident_id=?', (next_at, task['incident_id']))
            audit(conn, task['org_id'], 'worker', 'incident.reminder', task['incident_id'])
        conn.execute("UPDATE service_alerts SET status='resolved',updated_at=? WHERE kind='deadline' AND alert_key IN (SELECT 'due:' || id FROM incidents WHERE status IN ('resolved','false_positive'))", (now(),))


def fulfill_delete(db, request_id):
    with db.connect(write=True) as conn:
        row = conn.execute("SELECT * FROM privacy_requests WHERE id=? AND kind='delete' AND status='pending'", (request_id,)).fetchone()
        if not row:
            raise ValueError('Pending deletion request not found')
        org_id = row['org_id']
        sub = conn.execute('SELECT * FROM subscriptions WHERE org_id=?', (org_id,)).fetchone()
        if sub and sub['provider'] == 'stripe' and sub['status'] not in ('canceled', 'incomplete_expired'):
            raise ValueError('Cancel and reconcile the provider subscription before deletion')
        conn.execute('DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE org_id=?)', (org_id,))
        conn.execute('DELETE FROM verified_users WHERE user_id IN (SELECT id FROM users WHERE org_id=?)', (org_id,))
        for table in ('oidc_bindings', 'oidc_transactions', 'action_tokens', 'mail_jobs', 'tenant_integrations', 'incident_tasks',
                      'service_alerts', 'outbox', 'comments', 'events', 'incidents', 'exclusions', 'sources', 'audit',
                      'privacy_requests', 'billing_requests', 'usage_months', 'subscriptions', 'users'):
            conn.execute(f'DELETE FROM {table} WHERE org_id=?', (org_id,))
        conn.execute('DELETE FROM organizations WHERE id=?', (org_id,))
    return {'deleted_org_id': org_id, 'backups_removed': False}
