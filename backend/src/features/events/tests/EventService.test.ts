import { describe, expect, it } from 'vitest';
import { fixture } from './fixture.js';
import { loadEventConfigs } from '../configs/load.js';
import { EventValidator } from '../EventValidator.js';
import { AttendanceService } from '../../attendance/AttendanceService.js';
describe('server-authoritative event schedule and missions', () => {
  it('loads all event files and validates their cosmetic references', async () => {
    const events = await loadEventConfigs();
    expect(events).toHaveLength(4);
    events.forEach((e) => new EventValidator().validate(e));
  });
  it('uses inclusive start and exclusive end server-time boundaries', async () => {
    const f = fixture();
    f.setTime('2026-12-17T23:59:59.999+09:00');
    expect(f.events.getEventStatus(f.definition)).toBe('UPCOMING');
    await expect(
      f.rewards.claim('u', f.definition.id, f.definition.rewards[0]!.id),
    ).rejects.toThrow();
    f.setTime(f.definition.startAt);
    expect(f.events.getEventStatus(f.definition)).toBe('ACTIVE');
    expect(f.events.available(f.definition.id).id).toBe(f.definition.id);
    f.setTime(f.definition.endAt);
    expect(f.events.getEventStatus(f.definition)).toBe('ENDED');
    await expect(f.rewards.attendance('u', f.definition.id)).rejects.toThrow();
  });
  it('disables acquisition independently of calendar status', () => {
    const f = fixture();
    const event = { ...f.definition, active: false };
    f.events.replaceDefinitions([event]);
    expect(f.events.getEventStatus(event)).toBe('ACTIVE');
    expect(() => f.events.available(event.id)).toThrow();
  });
  it('rejects invalid dates, missing cosmetics, negative prices and foreign currencies', () => {
    const f = fixture();
    for (const edit of [
      (e: typeof f.definition) => {
        e.endAt = e.startAt;
      },
      (e: typeof f.definition) => {
        e.shop[0]!.price = -1;
      },
      (e: typeof f.definition) => {
        e.currency.eventId = 'other';
      },
      (e: typeof f.definition) => {
        e.cosmetics[0]!.cosmeticId = 'missing';
      },
    ]) {
      const e = structuredClone(f.definition);
      edit(e);
      expect(() => f.events.replaceDefinitions([e])).toThrow();
    }
  });
  it('tracks trusted game facts once and blocks duplicate mission claims', async () => {
    const f = fixture();
    const mission = f.definition.missions[0]!;
    const fact = {
      id: 'match:1:u:PLAY_GAME',
      userId: 'u',
      target: 'PLAY_GAME' as const,
      occurredAt: f.events.clock().toISOString(),
    };
    await f.missions.record(fact);
    await f.missions.record(fact);
    expect((await f.repository.read('u')).missions[mission.id]!.progress).toBe(1);
    await f.missions.claim('u', f.definition.id, mission.id);
    await expect(f.missions.claim('u', f.definition.id, mission.id)).rejects.toThrow('이미 수령');
    expect((await f.repository.read('u')).currencies[f.definition.currency.id]).toBe(20);
    expect((await f.repository.read('u')).participation[f.definition.id]!.missionsCompleted).toBe(
      1,
    );
    await expect(
      f.missions.claim('u', f.definition.id, f.definition.missions[2]!.id),
    ).rejects.toThrow('완료하지');
  });
  it('does not count facts outside the event window or after deactivation', async () => {
    const f = fixture();
    await f.missions.record({
      id: 'old',
      userId: 'u',
      target: 'WIN_GAME',
      occurredAt: '2026-01-01T00:00:00Z',
    });
    f.setTime(f.definition.endAt);
    await f.missions.record({
      id: 'ended',
      userId: 'u',
      target: 'WIN_GAME',
      occurredAt: f.events.clock().toISOString(),
    });
    expect((await f.repository.read('u')).missions).toEqual({});
  });
  it('separates normal attendance namespace from event attendance', async () => {
    const f = fixture();
    await f.repository.transaction('u', (account) =>
      new AttendanceService().claimDay(account, 'normal', f.events.clock(), 30),
    );
    await f.rewards.attendance('u', f.definition.id);
    const account = await f.repository.read('u');
    expect(account.attendance.normal).toHaveLength(1);
    expect(account.attendance[`event:${f.definition.id}`]).toHaveLength(1);
  });
  it('cannot claim completed mission rewards after event expiry', async () => {
    const f = fixture();
    await f.missions.record({
      id: 'win',
      userId: 'u',
      target: 'WIN_GAME',
      occurredAt: f.events.clock().toISOString(),
    });
    f.setTime(f.definition.endAt);
    await expect(
      f.missions.claim('u', f.definition.id, f.definition.missions[2]!.id),
    ).rejects.toThrow();
  });
});
