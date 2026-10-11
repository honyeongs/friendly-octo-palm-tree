"""Hosted checkout and verified, replay-safe provider reconciliation."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from netsec.monitor.database import audit, identifier, now
from netsec.monitor.dependencies import authorize, current_user
from netsec.monitor.security import rate_limit
from netsec.saas.identity import available, reauthenticate, sensitive_user
from netsec.saas.plans import PLANS, entitlement
from netsec.saas.schemas import Checkout, MockConfirm, Reauth

router = APIRouter(prefix='/api/saas')


def provider(settings):
    import stripe
    return stripe.StripeClient(settings.saas.stripe_key, max_network_retries=2, http_client=stripe.RequestsClient(timeout=10))


def end_time(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat(timespec='microseconds')


@router.get('/catalog')
def catalog(request: Request):
    settings = request.app.state.settings
    return {'enabled': settings.saas.enabled, 'billing_mode': settings.saas.billing_mode,
            'terms_version': settings.saas.terms_version, 'trial_days': 14,
            'public_launch': settings.saas.launch_confirmed,
            'local_mail': settings.saas.enabled and not settings.secure and settings.saas.mail_mode == 'local',
            'terms_url': settings.saas.terms_url, 'privacy_url': settings.saas.privacy_url,
            'items': [{'id': key, **value, 'price_configured': key in settings.saas.prices} for key, value in PLANS.items()]}


@router.get('/billing', dependencies=[Depends(available)])
def billing(request: Request, user=Depends(current_user)):
    authorize(user, 'admin')
    with request.app.state.db.connect() as conn:
        sub, plan, active = entitlement(conn, user['org_id'])
        usage = conn.execute('SELECT events FROM usage_months WHERE org_id=? AND month=?', (user['org_id'], now()[:7])).fetchone()
        seats = conn.execute('SELECT count(*) FROM users WHERE org_id=? AND active=1', (user['org_id'],)).fetchone()[0]
        sources = conn.execute('SELECT count(*) FROM sources WHERE org_id=? AND active=1', (user['org_id'],)).fetchone()[0]
        pending = conn.execute("SELECT id,plan,created_at FROM billing_requests WHERE org_id=? AND status='pending' ORDER BY created_at DESC LIMIT 1", (user['org_id'],)).fetchone()
    return {'subscription': {key: sub[key] for key in ('plan', 'status', 'trial_end', 'period_end', 'cancel_at_end', 'provider')},
            'active': active, 'limits': plan, 'usage': {'month': now()[:7], 'events': usage[0] if usage else 0, 'users': seats, 'sources': sources},
            'pending': dict(pending) if pending else None, 'mode': request.app.state.settings.saas.billing_mode}


@router.post('/billing/checkout', dependencies=[Depends(available)])
def checkout(payload: Checkout, request: Request, user=Depends(sensitive_user)):
    settings, db = request.app.state.settings, request.app.state.db
    rate_limit(db, 'checkout:' + user['org_id'], limit=5, seconds=300)
    with db.connect(write=True) as conn:
        reauthenticate(conn, user, payload.password)
        sub, _, _ = entitlement(conn, user['org_id'])
        if sub['provider'] == 'stripe' and sub['subscription_id'] and sub['status'] not in ('canceled', 'incomplete_expired'):
            raise HTTPException(409, '기존 구독은 결제 포털에서 변경하세요. 이중 구독은 허용하지 않습니다.')
        pending = conn.execute("SELECT id FROM billing_requests WHERE org_id=? AND status='pending'", (user['org_id'],)).fetchone()
        if pending:
            raise HTTPException(409, '진행 중인 결제가 있습니다. 기존 요청을 완료하거나 취소하세요.')
        if settings.saas.billing_mode == 'off':
            raise HTTPException(503, '결제 제공자가 아직 설정되지 않았습니다.')
        if settings.saas.billing_mode == 'stripe' and payload.plan not in settings.saas.prices:
            raise HTTPException(503, '요금제 가격 ID가 설정되지 않았습니다.')
        item_id = identifier()
        conn.execute('INSERT INTO billing_requests(id,org_id,plan,created_at) VALUES(?,?,?,?)', (item_id, user['org_id'], payload.plan, now()))
        audit(conn, user['org_id'], user['id'], 'billing.checkout', item_id, {'plan': payload.plan})
    if settings.saas.billing_mode == 'mock':
        return {'request_id': item_id, 'mode': 'mock', 'url': None}
    client = provider(settings)
    try:
        # Stable customer identity and idempotency survive retries and prevent cross-tenant binding.
        customer = sub['customer_id'] or client.v1.customers.create(
            {'metadata': {'netsec_org': user['org_id']}}, options={'idempotency_key': 'customer-' + user['org_id']}).id
        with db.connect(write=True) as conn:
            conn.execute("UPDATE subscriptions SET customer_id=?,provider='stripe' WHERE org_id=?", (customer, user['org_id']))
        session = client.v1.checkout.sessions.create({
            'mode': 'subscription', 'customer': customer, 'client_reference_id': item_id,
            'line_items': [{'price': settings.saas.prices[payload.plan], 'quantity': 1}],
            'subscription_data': {'metadata': {'netsec_request': item_id}},
            'success_url': settings.origin + '/#billing', 'cancel_url': settings.origin + '/#billing',
        }, options={'idempotency_key': 'checkout-' + item_id})
        with db.connect(write=True) as conn:
            conn.execute('UPDATE billing_requests SET provider_id=? WHERE id=?', (session.id, item_id))
        return {'request_id': item_id, 'mode': 'stripe', 'url': session.url}
    except Exception:
        # Preserve the request on ambiguous provider failure; operator can reconcile by idempotency key.
        raise HTTPException(502, '결제 연결에 실패했습니다. 동일 요청 ID로 운영자에게 확인을 요청하세요.') from None


@router.post('/billing/mock-confirm', dependencies=[Depends(available)])
def mock_confirm(payload: MockConfirm, request: Request, user=Depends(sensitive_user)):
    settings = request.app.state.settings
    if settings.secure or settings.saas.billing_mode != 'mock':
        raise HTTPException(404, '사용할 수 없습니다.')
    with request.app.state.db.connect(write=True) as conn:
        reauthenticate(conn, user, payload.password)
        row = conn.execute('SELECT * FROM billing_requests WHERE id=? AND org_id=?', (payload.request_id, user['org_id'])).fetchone()
        if not row or row['status'] != 'pending':
            raise HTTPException(409, '진행 중인 테스트 결제를 찾을 수 없습니다.')
        end = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(timespec='microseconds')
        conn.execute("UPDATE subscriptions SET plan=?,status='active',provider='mock',period_end=?,cancel_at_end=0,updated_at=? WHERE org_id=?", (row['plan'], end, now(), user['org_id']))
        conn.execute("UPDATE billing_requests SET status='completed' WHERE id=?", (row['id'],))
        audit(conn, user['org_id'], user['id'], 'billing.mock_confirm', row['id'])
    return {'ok': True, 'charged': False}


@router.post('/billing/portal', dependencies=[Depends(available)])
def portal(payload: Reauth, request: Request, user=Depends(sensitive_user)):
    settings = request.app.state.settings
    with request.app.state.db.connect(write=True) as conn:
        reauthenticate(conn, user, payload.password)
        sub, _, _ = entitlement(conn, user['org_id'])
        audit(conn, user['org_id'], user['id'], 'billing.portal')
    if settings.saas.billing_mode != 'stripe' or not sub['customer_id']:
        raise HTTPException(409, '연결된 결제 고객이 없습니다.')
    try:
        session = provider(settings).v1.billing_portal.sessions.create({'customer': sub['customer_id'], 'return_url': settings.origin + '/#billing'})
        return {'url': session.url}
    except Exception:
        raise HTTPException(502, '결제 포털 연결에 실패했습니다.') from None


@router.post('/billing/cancel', dependencies=[Depends(available)])
def cancel(payload: Reauth, request: Request, user=Depends(sensitive_user)):
    settings = request.app.state.settings
    with request.app.state.db.connect(write=True) as conn:
        reauthenticate(conn, user, payload.password)
        sub, _, _ = entitlement(conn, user['org_id'])
    if sub['provider'] == 'stripe' and sub['subscription_id']:
        try:
            provider(settings).v1.subscriptions.update(sub['subscription_id'], {'cancel_at_period_end': True})
        except Exception:
            raise HTTPException(502, '해지 요청에 실패했습니다. 결제 포털에서 확인하세요.') from None
    with request.app.state.db.connect(write=True) as conn:
        conn.execute('UPDATE subscriptions SET cancel_at_end=1,updated_at=? WHERE org_id=?', (now(), user['org_id']))
        if sub['provider'] != 'stripe':
            conn.execute("UPDATE billing_requests SET status='canceled' WHERE org_id=? AND status='pending'", (user['org_id'],))
        audit(conn, user['org_id'], user['id'], 'billing.cancel')
    return {'ok': True, 'period_end': sub['period_end']}


def reconcile(db, settings, event, client):
    if not isinstance(event, dict):
        event = event.to_dict()
    event_id = event['id']
    if event.get('livemode', False) != settings.saas.stripe_key.startswith(('sk_live_', 'rk_live_')):
        raise HTTPException(400, '결제 환경이 일치하지 않습니다.')
    with db.connect() as conn:
        if conn.execute('SELECT 1 FROM billing_events WHERE event_id=?', (event_id,)).fetchone():
            return {'duplicate': True}
    obj, event_type = event['data']['object'], event['type']
    if event_type.startswith('customer.subscription.'):
        sub_id = obj['id']
    elif event_type in ('checkout.session.completed', 'checkout.session.async_payment_succeeded'):
        sub_id = obj.get('subscription')
    else:
        return {'ignored': True}
    if not sub_id:
        return {'ignored': True}
    # Serialize retrieval + update so two deliveries cannot apply stale snapshots out of order.
    with db.connect(write=True) as conn:
        if conn.execute('SELECT 1 FROM billing_events WHERE event_id=?', (event_id,)).fetchone():
            return {'duplicate': True}
        current = client.v1.subscriptions.retrieve(sub_id)
        if not isinstance(current, dict):
            current = current.to_dict()
        row = conn.execute('SELECT * FROM subscriptions WHERE customer_id=?', (current['customer'],)).fetchone()
        if not row:
            raise HTTPException(409, '등록되지 않은 결제 고객입니다.')
        request_id = current.get('metadata', {}).get('netsec_request', '')
        checkout_row = conn.execute('SELECT * FROM billing_requests WHERE id=? AND org_id=?', (request_id, row['org_id'])).fetchone()
        if not checkout_row or (row['subscription_id'] and row['subscription_id'] != sub_id and row['status'] not in ('canceled', 'incomplete_expired')):
            raise HTTPException(409, '구독 연결이 일치하지 않습니다.')
        items = current['items']['data']
        if len(items) != 1 or items[0].get('quantity', 1) != 1:
            raise HTTPException(409, '지원하지 않는 구독 구성입니다.')
        price = items[0]['price']['id']
        plan = next((key for key, value in settings.saas.prices.items() if value == price), None)
        if not plan:
            raise HTTPException(409, '등록되지 않은 결제 가격입니다.')
        period = items[0].get('current_period_end') or current.get('current_period_end')
        if not period:
            raise HTTPException(409, '결제 기간을 확인할 수 없습니다.')
        conn.execute("UPDATE subscriptions SET plan=?,status=?,subscription_id=?,period_end=?,cancel_at_end=?,provider='stripe',updated_at=? WHERE org_id=?",
                     (plan, current['status'], sub_id, end_time(period), int(current.get('cancel_at_period_end', False)), now(), row['org_id']))
        conn.execute("UPDATE billing_requests SET status='completed' WHERE id=?", (request_id,))
        conn.execute('INSERT INTO billing_events VALUES(?,?)', (event_id, now()))
        audit(conn, row['org_id'], 'payment-provider', 'billing.reconcile', request_id, {'status': current['status'], 'plan': plan})
    return {'ok': True}


@router.post('/billing/webhook', dependencies=[Depends(available)])
async def webhook(request: Request):
    settings = request.app.state.settings
    if settings.saas.billing_mode != 'stripe':
        raise HTTPException(404, '사용할 수 없습니다.')
    import stripe
    from starlette.concurrency import run_in_threadpool
    raw = await request.body()
    try:
        event = stripe.Webhook.construct_event(raw, request.headers.get('stripe-signature', ''), settings.saas.stripe_webhook_secret, tolerance=300)
    except Exception:
        raise HTTPException(400, '결제 서명 검증에 실패했습니다.') from None
    return await run_in_threadpool(reconcile, request.app.state.db, settings, event, provider(settings))
