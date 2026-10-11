"""Server-enforced entitlements and UTC calendar-month usage accounting."""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from netsec.monitor.database import now

PLANS = {
    'starter': {'name': 'Starter', 'events': 100000, 'users': 5, 'sources': 10, 'retention_days': 30},
    'team': {'name': 'Team', 'events': 1000000, 'users': 20, 'sources': 50, 'retention_days': 90},
    'business': {'name': 'Business', 'events': 5000000, 'users': 100, 'sources': 100, 'retention_days': 365},
}


def provision(conn, org_id):
    end = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat(timespec='microseconds')
    conn.execute("INSERT INTO subscriptions(org_id,plan,status,trial_end,period_end,updated_at) VALUES(?,'starter','trialing',?,?,?) ON CONFLICT(org_id) DO NOTHING",
                 (org_id, end, end, now()))


def entitlement(conn, org_id, *, require_active=False):
    row = conn.execute('SELECT * FROM subscriptions WHERE org_id=?', (org_id,)).fetchone()
    if row is None:
        raise HTTPException(409, 'SaaS 요금제 이전이 필요합니다. 운영자에게 문의하세요.')
    sub = dict(row)
    active = sub['status'] in ('active', 'trialing') and sub['period_end'] > now()
    if require_active and not active:
        raise HTTPException(402, '체험 또는 구독이 종료되었습니다. 구독 상태를 확인하세요.')
    return sub, PLANS[sub['plan']], active


def reserve_events(conn, org_id, count):
    if count == 0:
        return
    _, plan, _ = entitlement(conn, org_id, require_active=True)
    month = now()[:7]
    conn.execute('INSERT INTO usage_months(org_id,month,events) VALUES(?,?,0) ON CONFLICT(org_id,month) DO NOTHING', (org_id, month))
    changed = conn.execute('UPDATE usage_months SET events=events+? WHERE org_id=? AND month=? AND events+?<=?',
                           (count, org_id, month, count, plan['events'])).rowcount
    if not changed:
        raise HTTPException(402, '월 수집량 한도에 도달했습니다. 배치 전체를 취소했습니다.')


def check_capacity(conn, org_id, resource):
    _, plan, _ = entitlement(conn, org_id, require_active=True)
    if resource == 'users':
        count = conn.execute('SELECT count(*) FROM users WHERE org_id=? AND active=1', (org_id,)).fetchone()[0]
        count += conn.execute("SELECT count(*) FROM action_tokens WHERE org_id=? AND purpose='invite' AND expires_at>?", (org_id, now())).fetchone()[0]
    else:
        count = conn.execute('SELECT count(*) FROM sources WHERE org_id=? AND active=1', (org_id,)).fetchone()[0]
    if count >= plan[resource]:
        raise HTTPException(402, '요금제의 ' + resource + ' 한도에 도달했습니다.')
