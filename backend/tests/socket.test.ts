import { afterEach, describe, expect, it } from 'vitest';
import { AIDifficulty, GameMode } from '../../shared/src/index.js';
import { AIService } from '../src/ai/AIService.js';
import { seededRandom } from '../src/engine/random.js';
import { createApp } from '../src/server/app.js';
import { parseAction, parseCreate } from '../src/server/validation.js';
import { TestClient } from './socket-client.js';
import { fixture as eventFixture } from '../src/features/events/tests/fixture.js';
import type { EventDashboard } from '../../shared/src/events.js';
describe('authoritative multiplayer sockets', () => {
  let app: ReturnType<typeof createApp>;
  const clients: TestClient[] = [];
  let url: string;
  afterEach(async () => {
    clients.forEach((c) => c.socket.disconnect());
    clients.length = 0;
    await app?.close();
  });
  async function server(options: Parameters<typeof createApp>[0] = {}) {
    app = createApp({
      maxRequestsPerSecond: 10000,
      engineOptions: () => ({ random: seededRandom(42) }),
      ...options,
    });
    await new Promise<void>((resolve) => app.httpServer.listen(0, '127.0.0.1', resolve));
    const address = app.httpServer.address();
    if (!address || typeof address === 'string') throw new Error('No port');
    url = `http://127.0.0.1:${address.port}`;
  }
  async function connect(token?: string) {
    const c = new TestClient(url, token);
    clients.push(c);
    await c.connect();
    return c;
  }
  async function pair(mode = GameMode.ONE_VS_ONE) {
    const a = await connect();
    const b = await connect();
    await a.ok('create_room', { nickname: 'Alpha', mode });
    await b.ok('join_room', { roomId: a.lobby!.room!.roomId, nickname: 'Beta' });
    await a.until(() => a.lobby!.room!.members.length === 2);
    return { a, b };
  }
  async function start(a: TestClient, b: TestClient) {
    await a.ok('ready', { ready: true });
    await b.ok('ready', { ready: true });
    await a.ok('start_game');
    await b.until(() => !!b.view);
  }
  it('verifies event identity, prices and time, and derives missions from committed game actions', async () => {
    const f = eventFixture(); await server({ eventSystem: Promise.resolve(f) });
    const { a, b } = await pair(); await start(a, b);
    const received: { data?: EventDashboard } = {};
    a.socket.on('events_updated', data => { received.data = data; });
    await a.ok('event_reward_claim', { eventId: f.definition.id, itemId: f.definition.rewards[0]!.id, userId: b.session!.playerId, amount: 99999999 });
    expect(received.data!.account.userId).toBe(a.session!.playerId);
    expect(received.data!.account.currencies[f.definition.currency.id]).toBe(1000);
    expect((await f.repository.read(b.session!.playerId)).currencies).toEqual({});
    await a.ok('event_shop_buy', { eventId: f.definition.id, itemId: f.definition.shop[0]!.id, price: 0, amount: 99999 });
    expect(received.data!.account.currencies[f.definition.currency.id]).toBe(500);
    expect((await a.send('event_mission_claim', { eventId: f.definition.id, itemId: f.definition.missions[0]!.id, progress: 100 })).ok).toBe(false);
    await a.ok('roll_dice', a.actionRequest()); await a.ok('buy_property', a.actionRequest());
    await expect.poll(async () => (await f.repository.read(a.session!.playerId)).missions[f.definition.missions[3]!.id]?.progress).toBe(1);
    f.setTime(f.definition.endAt);
    expect((await a.send('event_shop_buy', { eventId: f.definition.id, itemId: f.definition.shop[1]!.id, now: f.definition.startAt, endAt: '2099-01-01T00:00:00Z' })).ok).toBe(false);
    await a.ok('cosmetic_equip', { eventId: f.definition.id, itemId: f.definition.shop[0]!.itemId });
    expect(received.data!.account.equipped.DICE_SKIN).toBe(f.definition.shop[0]!.itemId);
  });
  it('finishes a full default-rules 1vs1 with two human sessions and identical snapshots', async () => {
    await server();
    const { a, b } = await pair();
    await start(a, b);
    expect(a.session!.playerId).not.toBe(a.socket.id);
    expect(a.view!.room.players.every((p) => !p.isAI)).toBe(true);
    const controller = new AIService(); // Test driver only; both server participants remain human.
    let actions = 0;
    while (a.view!.room.status === 'PLAYING' && actions++ < 5000) {
      const current = a.view!.room.currentTurnPlayerId === a.session!.playerId ? a : b;
      const action = controller.decide(current.view!.room, current.view!.options);
      const event = {
        ROLL: 'roll_dice',
        BUY: 'buy_property',
        UPGRADE: 'upgrade_property',
        END_TURN: 'end_turn',
      } as const;
      const revision = current.view!.room.gameState.revision + 1;
      await current.ok(event[action.type], current.actionRequest());
      await Promise.all([
        a.until(() => a.view!.room.gameState.revision === revision),
        b.until(() => b.view!.room.gameState.revision === revision),
      ]);
      expect(a.view!.room).toEqual(b.view!.room);
    }
    await Promise.all([a.until(() => !!a.finished), b.until(() => !!b.finished)]);
    expect(a.finished).toEqual(b.finished);
    expect(a.finished!.gameState.winnerIds).toHaveLength(1);
    expect(a.finished!.gameState.bankruptcyOrder).toHaveLength(1);
    expect(a.finished!.turnNumber).toBeLessThan(2000);
    for (const event of [
      'game_started',
      'dice_rolled',
      'player_moved',
      'tile_resolved',
      'player_bankrupt',
    ])
      expect(a.events).toContain(event);
    expect((await a.send('roll_dice', a.actionRequest())).ok).toBe(false);
  }, 20000);
  it('ignores forged state and blocks impersonation, outsiders, duplicates and stale commands', async () => {
    await server();
    const { a, b } = await pair();
    const outsider = await connect();
    await start(a, b);
    const initial = structuredClone(a.view!.room);
    expect(
      (await b.send('roll_dice', { ...b.actionRequest(), playerId: a.session!.playerId })).ok,
    ).toBe(false);
    expect((await outsider.send('roll_dice', a.actionRequest())).ok).toBe(false);
    expect(a.view!.room).toEqual(initial);
    const request = a.actionRequest();
    await a.ok('roll_dice', {
      ...request,
      playerId: b.session!.playerId,
      money: 999999999,
      position: 31,
      diceResult: [6, 6],
      action: { type: 'SET_MONEY' },
    });
    expect(a.view!.room.gameState.lastRoll!.dice).toEqual([4, 3]);
    expect(a.view!.room.players[0]!.position).toBe(7);
    expect(a.view!.room.players[0]!.money).toBe(1600);
    expect((await a.send('roll_dice', request)).ok).toBe(false);
    expect((await a.send('roll_dice', a.actionRequest())).ok).toBe(false);
    expect((await a.send('buy_property', { ...a.actionRequest(), roomId: 'FFFFFFFF' })).ok).toBe(
      false,
    );
    await a.ok('buy_property', { ...a.actionRequest(), purchasePrice: 0, money: 999999 });
    expect(a.view!.room.players[0]!.money).toBe(1380);
  });
  it('enforces capacity, readiness, host start and locks running rooms', async () => {
    await server();
    const { a, b } = await pair();
    const c = await connect();
    const code = a.lobby!.room!.roomId;
    expect((await c.send('join_room', { roomId: code, nickname: 'Extra' })).ok).toBe(false);
    expect((await a.send('start_game')).ok).toBe(false);
    await a.ok('ready', { ready: true });
    await b.ok('ready', { ready: true });
    expect((await b.send('start_game')).ok).toBe(false);
    await a.ok('start_game');
    expect((await a.send('start_game')).ok).toBe(false);
    expect((await b.send('ready', { ready: false })).ok).toBe(false);
    expect((await c.send('join_room', { roomId: code, nickname: 'Late' })).ok).toBe(false);
  });
  it('supports four players and transfers host when leaving', async () => {
    await server();
    const { a, b } = await pair(GameMode.FOUR_PLAYER_FFA);
    const code = a.lobby!.room!.roomId;
    const c = await connect();
    const d = await connect();
    const extra = await connect();
    for (const [client, nickname] of [
      [c, 'C'],
      [d, 'D'],
    ] as const)
      await client.ok('join_room', { roomId: code, nickname });
    expect((await extra.send('join_room', { roomId: code, nickname: 'Extra' })).ok).toBe(false);
    await a.ok('leave_room');
    await b.until(() => b.lobby!.room!.hostPlayerId === b.session!.playerId);
    expect(b.lobby!.room!.members).toHaveLength(3);
    await extra.ok('join_room', { roomId: code, nickname: 'Extra' });
    for (const client of [b, c, d, extra]) await client.ok('ready', { ready: true });
    await b.ok('start_game');
    expect(b.view!.room.players).toHaveLength(4);
  });
  it('pauses on disconnect and restores the same identity and game', async () => {
    await server({ reconnectGraceMs: 3000 });
    const { a, b } = await pair();
    await start(a, b);
    const before = structuredClone(b.view!.room);
    const token = a.session!.sessionToken;
    const oldSocket = a.socket.id;
    a.socket.disconnect();
    await b.until(() => !!b.lobby!.room!.paused);
    expect((await b.send('roll_dice', b.actionRequest())).ok).toBe(false);
    const restored = await connect(token);
    await restored.until(() => !!restored.view);
    expect(restored.socket.id).not.toBe(oldSocket);
    expect(restored.session!.playerId).toBe(a.session!.playerId);
    expect(restored.view!.room).toEqual(before);
    expect(restored.view!.options.canRoll).toBe(true);
    await restored.ok('roll_dice', restored.actionRequest());
  });
  it('rejects a second active connection using the same session', async () => {
    await server();
    const a = await connect();
    const duplicate = new TestClient(url, a.session!.sessionToken);
    clients.push(duplicate);
    await expect(duplicate.connect()).rejects.toThrow('SESSION_IN_USE');
    expect(a.socket.connected).toBe(true);
  });
  it('hands an expired disconnected turn to AI and resumes the other player', async () => {
    await server({ reconnectGraceMs: 40, aiDelayMs: 1 });
    const { a, b } = await pair();
    await start(a, b);
    a.socket.disconnect();
    await b.until(
      () => b.view!.room.currentTurnPlayerId === b.session!.playerId && b.view!.room.turnNumber > 1,
    );
    expect(b.lobby!.room!.paused).toBe(false);
    expect(b.lobby!.room!.members.find((p) => p.playerId === a.session!.playerId)!.control).toBe(
      'AI',
    );
    expect(b.view!.room.players[0]!.isAI).toBe(false);
    const expired = new TestClient(url, a.session!.sessionToken);
    clients.push(expired);
    await expired.connect();
    expect(expired.session!.playerId).toBe(a.session!.playerId);
    expect(expired.lobby!.room).toBeNull();
  });
  it('cleans abandoned waiting rooms and isolates broadcasts', async () => {
    await server({ reconnectGraceMs: 40 });
    const { a, b } = await pair();
    const code = a.lobby!.room!.roomId;
    const outsider = await connect();
    await outsider.ok('create_room', { nickname: 'Other', mode: GameMode.ONE_VS_ONE });
    const ownCode = outsider.lobby!.room!.roomId;
    a.socket.disconnect();
    await b.until(() => b.lobby!.room!.members.length === 1);
    expect(b.lobby!.room!.hostPlayerId).toBe(b.session!.playerId);
    await b.ok('leave_room');
    expect(b.lobby!.room).toBeNull();
    expect((await b.send('join_room', { roomId: code, nickname: 'Back' })).ok).toBe(false);
    expect(outsider.lobby!.room!.roomId).toBe(ownCode);
    expect(outsider.view).toBeUndefined();
  });
  it('preserves solo AI mode through the common manager', async () => {
    await server({ aiDelayMs: 1 });
    const a = await connect();
    await a.ok('create_room', {
      nickname: 'Solo',
      mode: GameMode.SOLO_AI,
      aiCount: 3,
      difficulty: AIDifficulty.NORMAL,
    });
    await a.ok('roll_dice', a.actionRequest());
    await a.ok('end_turn', a.actionRequest());
    await a.until(
      () => a.view!.room.currentTurnPlayerId === a.session!.playerId && a.view!.room.turnNumber > 1,
    );
    expect(a.view!.room.players).toHaveLength(4);
    expect(a.view!.options.canRoll).toBe(true);
  });
  it('limits command spam and validates malformed payloads', async () => {
    await server({ maxRequestsPerSecond: 2 });
    const a = await connect();
    await a.ok('create_room', { nickname: 'Rate', mode: GameMode.ONE_VS_ONE });
    await a.ok('ready', { ready: true });
    expect((await a.send('ready', { ready: false })).ok).toBe(false);
    for (const input of [null, {}, { nickname: ' ', mode: 'ONE_VS_ONE' }])
      expect(() => parseCreate(input)).toThrow();
    for (const input of [null, {}, { roomId: '12345678', expectedRevision: -1 }])
      expect(() => parseAction(input)).toThrow();
  });
});
