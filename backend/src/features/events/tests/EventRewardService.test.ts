import { afterEach, describe, expect, it } from 'vitest';
import { mkdtempSync, rmSync } from 'node:fs';
import { join, resolve, sep } from 'node:path';
import { tmpdir } from 'node:os';
import { fixture } from './fixture.js';
import { InventoryService } from '../../inventory/InventoryService.js';
import { SessionStore } from '../../../server/SessionStore.js';
describe('atomic event rewards, inventory and purchase security', () => {
  const directories: string[] = [];
  afterEach(() => {
    for (const directory of directories) {
      if (!resolve(directory).startsWith(resolve(tmpdir()) + sep))
        throw new Error('Unsafe cleanup target');
      rmSync(directory, { recursive: true, force: true });
    }
    directories.length = 0;
  });
  it('credits server-configured currency and debits the configured shop price', async () => {
    const f = fixture();
    await f.rewards.claim('u', f.definition.id, f.definition.rewards[0]!.id);
    expect((await f.repository.read('u')).currencies[f.definition.currency.id]).toBe(1000);
    await f.shop.buy('u', f.definition.id, f.definition.shop[0]!.id);
    const a = await f.repository.read('u');
    expect(a.currencies[f.definition.currency.id]).toBe(500);
    expect(a.inventory[f.definition.shop[0]!.itemId]).toBeDefined();
    expect(a.history).toHaveLength(2);
  });
  it('enforces purchase limit and prevents concurrent double-spend/grants', async () => {
    const f = fixture();
    await f.rewards.claim('u', f.definition.id, f.definition.rewards[0]!.id);
    const results = await Promise.allSettled([
      f.shop.buy('u', f.definition.id, f.definition.shop[0]!.id),
      f.shop.buy('u', f.definition.id, f.definition.shop[0]!.id),
    ]);
    expect(results.filter((r) => r.status === 'fulfilled')).toHaveLength(1);
    const a = await f.repository.read('u');
    expect(a.currencies[f.definition.currency.id]).toBe(500);
    expect(a.purchases[f.definition.shop[0]!.id]).toBe(1);
  });
  it('rolls back insufficient-funds purchase without inventory or receipts', async () => {
    const f = fixture();
    const before = await f.repository.read('u');
    await expect(f.shop.buy('u', f.definition.id, f.definition.shop[0]!.id)).rejects.toThrow(
      '부족',
    );
    expect(await f.repository.read('u')).toEqual(before);
  });
  it('blocks both shop purchase and new cosmetic acquisition after expiry', async () => {
    const f = fixture();
    await f.rewards.claim('u', f.definition.id, f.definition.rewards[0]!.id);
    f.setTime(f.definition.endAt);
    await expect(f.shop.buy('u', f.definition.id, f.definition.shop[0]!.id)).rejects.toThrow();
    expect((await f.repository.read('u')).inventory).toEqual({});
  });
  it('enforces a cosmetic acquisition window narrower than its event', async () => {
    const f = fixture();
    const event = structuredClone(f.definition);
    event.cosmetics[0]!.availableUntil = '2026-12-19T00:00:00+09:00';
    f.events.replaceDefinitions([event]);
    await f.rewards.claim('u', event.id, event.rewards[0]!.id);
    await expect(f.shop.buy('u', event.id, event.shop[0]!.id)).rejects.toThrow('획득');
    expect((await f.repository.read('u')).currencies[event.currency.id]).toBe(1000);
  });
  it('keeps owned skins equippable after the event ends', async () => {
    const f = fixture();
    await f.rewards.claim('u', f.definition.id, f.definition.rewards[0]!.id);
    await f.shop.buy('u', f.definition.id, f.definition.shop[0]!.id);
    f.setTime('2028-01-01T00:00:00Z');
    await f.repository.transaction('u', (account) =>
      new InventoryService().equip(account, f.definition.shop[0]!.itemId),
    );
    expect((await f.events.dashboard('u')).account.equipped.DICE_SKIN).toBe(
      f.definition.shop[0]!.itemId,
    );
    await expect(
      f.repository.transaction('other', (a) =>
        new InventoryService().equip(a, f.definition.shop[0]!.itemId),
      ),
    ).rejects.toThrow('보유하지');
  });
  it('prevents duplicate attendance and permits a new Korea calendar day', async () => {
    const f = fixture();
    await f.rewards.attendance('u', f.definition.id);
    await expect(f.rewards.attendance('u', f.definition.id)).rejects.toThrow('이미');
    f.setTime('2026-12-21T00:00:00+09:00');
    await f.rewards.attendance('u', f.definition.id);
    expect((await f.repository.read('u')).coins).toBe(100);
    expect((await f.repository.read('u')).currencies[f.definition.currency.id]).toBe(50);
  });
  it('claims all seven attendance rewards including box and permanent dice', async () => {
    const f = fixture();
    for (let day = 20; day <= 26; day++) {
      f.setTime(`2026-12-${day}T00:00:00+09:00`);
      await f.rewards.attendance('u', f.definition.id);
    }
    const a = await f.repository.read('u');
    expect(a.boxes.festival_box).toBe(1);
    expect(a.inventory.christmas_2026_dice).toBeDefined();
    expect(a.coins).toBe(400);
  });
  it('allows only one claim under simultaneous reward requests', async () => {
    const f = fixture();
    const results = await Promise.allSettled(
      Array.from({ length: 8 }, () =>
        f.rewards.claim('u', f.definition.id, f.definition.rewards[0]!.id),
      ),
    );
    expect(results.filter((r) => r.status === 'fulfilled')).toHaveLength(1);
    expect((await f.repository.read('u')).history).toHaveLength(1);
  });
  it('persists ownership, receipts and hashed guest identity across service restart', async () => {
    const directory = mkdtempSync(join(tmpdir(), 'starlane-events-'));
    directories.push(directory);
    const identities = join(directory, 'identities.json');
    const store = new SessionStore(identities);
    const session = store.connect(undefined, 'old');
    const f = fixture(join(directory, 'accounts'));
    await f.rewards.claim(session.playerId, f.definition.id, f.definition.rewards[0]!.id);
    await f.shop.buy(session.playerId, f.definition.id, f.definition.shop[0]!.id);
    const restoredSession = new SessionStore(identities).connect(session.token, 'new');
    expect(restoredSession.playerId).toBe(session.playerId);
    const restored = fixture(join(directory, 'accounts'));
    restored.setTime('2028-01-01T00:00:00Z');
    await restored.repository.transaction(session.playerId, (a) =>
      new InventoryService().equip(a, 'christmas_2026_dice'),
    );
    expect((await restored.repository.read(session.playerId)).history).toHaveLength(2);
  });
});
