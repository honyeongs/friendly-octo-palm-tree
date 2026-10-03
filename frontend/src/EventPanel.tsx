import { useEffect, useState } from 'react';
import type { EventDashboard, RewardSpec } from '../../shared/src/events';
type Action =
  | 'event_shop_buy'
  | 'event_mission_claim'
  | 'event_reward_claim'
  | 'event_attendance_claim'
  | 'cosmetic_equip';
interface Props {
  data: EventDashboard | null;
  active: boolean;
  action: (type: Action, eventId: string, itemId?: string) => void;
  refresh: () => void;
}
export function EventPanel({ data, active, action, refresh }: Props) {
  const [collection, setCollection] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const start = performance.now();
    setElapsed(0);
    const timer = setInterval(() => setElapsed(performance.now() - start), 1000);
    return () => clearInterval(timer);
  }, [data?.serverTime]);
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 15000);
    return () => clearInterval(timer);
  }, []);
  if (!data)
    return (
      <section className="panel waiting-room">
        <h1>이벤트 정보를 불러오는 중입니다.</h1>
        <button disabled={!active} onClick={refresh}>
          다시 불러오기
        </button>
      </section>
    );
  const { account } = data;
  const cosmetic = (id: string) => data.cosmetics.find((c) => c.id === id);
  const rewardLabel = (r: RewardSpec) =>
    `${r.rewardType === 'COSMETIC' ? cosmetic(r.rewardId)?.name : r.rewardType === 'COIN' ? 'Coin' : r.rewardType === 'BOX' ? '기념 보상 상자' : (data.events.find((e) => e.definition.currency.id === r.rewardId)?.definition.currency.name ?? r.rewardId)} × ${r.rewardAmount}`;
  const current = data.events.filter(
    (e) => e.definition.active && e.status === 'ACTIVE' && e.remainingMs > elapsed,
  );
  const countdown = (remainingMs: number) => {
    const total = Math.max(0, Math.floor((remainingMs - elapsed) / 1000));
    return `${Math.floor(total / 86400)}D ${String(Math.floor(total / 3600) % 24).padStart(2, '0')}:${String(Math.floor(total / 60) % 60).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
  };
  return (
    <section className="event-page">
      <div className="game-heading">
        <div>
          <span className="eyebrow">SEASONAL VOYAGES</span>
          <h1>{collection ? '별길 컬렉션' : '기간 한정 이벤트'}</h1>
        </div>
        <div className="event-nav">
          <button onClick={() => setCollection(false)}>EVENT</button>
          <button onClick={() => setCollection(true)}>COLLECTION</button>
          <button disabled={!active} onClick={refresh}>
            새로고침
          </button>
        </div>
      </div>
      <p>
        계정 Coin: {account.coins} · 보상 상자:{' '}
        {Object.values(account.boxes).reduce((a, b) => a + b, 0)} · 획득 기록{' '}
        {account.history.length}건
      </p>
      {collection ? (
        data.events.map(({ definition: e, status }) => (
          <section className="panel" key={e.id}>
            <h2>
              {e.name} · {status}
            </h2>
            <div className="event-cards">
              {[...new Set(e.cosmetics.map((c) => c.cosmeticId))].map((id) => {
                const skin = cosmetic(id)!;
                const owned = !!account.inventory[id];
                const equipped = account.equipped[skin.cosmeticType] === id;
                return (
                  <article className="cosmetic-card" key={id}>
                    <img src={skin.imageUrl} alt="" />
                    <h3>{skin.name}</h3>
                    <span className="limited">LIMITED</span> <small>{skin.rarity}</small>
                    <p>{owned ? '✓ OWNED' : '🔒 미보유'}</p>
                    <button
                      disabled={!active || !owned || equipped}
                      onClick={() => action('cosmetic_equip', e.id, id)}
                    >
                      {equipped ? '장착 중' : '장착'}
                    </button>
                  </article>
                );
              })}
            </div>
          </section>
        ))
      ) : current.length === 0 ? (
        <section className="panel">
          <h2>현재 진행 중인 이벤트가 없습니다.</h2>
          <p>컬렉션에서 지난 이벤트 기념품과 예정된 스킨을 확인할 수 있습니다.</p>
        </section>
      ) : (
        current.map(({ definition: e, remainingMs }) => (
          <section className="event-festival panel" key={e.id}>
            <div
              className="event-banner"
              style={{
                backgroundImage: `linear-gradient(90deg,#183731df,#18373188),url(${e.bannerImageUrl})`,
              }}
            >
              <span className="eyebrow">{e.theme}</span>
              <h2>{e.name}</h2>
              <p>{e.description}</p>
              <strong>이벤트 종료까지 {countdown(remainingMs)}</strong>
              <p>
                {e.currency.name}: {account.currencies[e.currency.id] ?? 0}
              </p>
            </div>
            <h2>이벤트 출석</h2>
            <p>
              한국 시간 기준 하루 1회 · 누적 {(account.attendance[`event:${e.id}`] ?? []).length} /{' '}
              {e.attendance.length}일
            </p>
            <div className="attendance-days">
              {e.attendance.map((reward, index) => (
                <div key={index}>
                  Day {index + 1}
                  <small>{rewardLabel(reward)}</small>
                  {index < (account.attendance[`event:${e.id}`]?.length ?? 0) ? '✓ 수령' : ''}
                </div>
              ))}
            </div>
            <button
              disabled={
                !active || (account.attendance[`event:${e.id}`]?.length ?? 0) >= e.attendance.length
              }
              onClick={() => action('event_attendance_claim', e.id)}
            >
              오늘 출석 보상 받기
            </button>
            <h2>이벤트 미션</h2>
            <div className="event-cards">
              {e.missions.map((m) => {
                const progress = account.missions[m.id];
                return (
                  <article key={m.id} className="cosmetic-card">
                    <h3>{m.title}</h3>
                    <p>{m.description}</p>
                    <p>
                      {progress?.progress ?? 0} / {m.targetAmount}
                    </p>
                    <small>{rewardLabel(m)}</small>
                    <button
                      disabled={
                        !active || !!progress?.claimed || (progress?.progress ?? 0) < m.targetAmount
                      }
                      onClick={() => action('event_mission_claim', e.id, m.id)}
                    >
                      {progress?.claimed ? '수령 완료' : '미션 보상 받기'}
                    </button>
                  </article>
                );
              })}
            </div>
            <h2>이벤트 상점</h2>
            <div className="event-cards">
              {e.shop.map((item) => {
                const skin = cosmetic(item.itemId)!;
                const owned = !!account.inventory[skin.id];
                return (
                  <article key={item.id} className="cosmetic-card">
                    <img src={skin.imageUrl} alt="" />
                    <h3>{skin.name}</h3>
                    <span className="limited">LIMITED</span> <small>{skin.rarity}</small>
                    <p>
                      {item.price} {e.currency.name} · 계정당 {item.purchaseLimit}회
                    </p>
                    <button
                      disabled={!active || owned}
                      onClick={() => action('event_shop_buy', e.id, item.id)}
                    >
                      {owned ? 'OWNED' : '구매'}
                    </button>
                  </article>
                );
              })}
            </div>
            <h2>이벤트 보상</h2>
            {e.rewards.map((r) => (
              <div className="event-gift" key={r.id}>
                <span>
                  {r.title} · {rewardLabel(r)}
                </span>
                <button
                  disabled={!active || account.claims.includes(`reward:${e.id}:${r.id}`)}
                  onClick={() => action('event_reward_claim', e.id, r.id)}
                >
                  {account.claims.includes(`reward:${e.id}:${r.id}`) ? '수령 완료' : '선물 받기'}
                </button>
              </div>
            ))}
          </section>
        ))
      )}
      <section className="panel">
        <h2>최근 보상 기록</h2>
        {account.history
          .slice(-10)
          .reverse()
          .map((h) => (
            <p key={h.id}>
              {h.grantedAt} · {rewardLabel(h.reward)} · {h.source}
            </p>
          ))}
        <small>
          획득 기간은 서버에서 확인합니다. 이미 보유한 스킨은 이벤트가 끝나도 컬렉션에서 장착할 수
          있습니다. 상자는 보유 수량만 제공하며 개봉 기능은 후속 단계입니다.
        </small>
      </section>
    </section>
  );
}
