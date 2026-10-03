import { describe, expect, it } from 'vitest';
import { AIDifficulty, GameMode } from '../../shared/src/index.js';
import { GameEngine } from '../src/engine/GameEngine.js';
import { seededRandom } from '../src/engine/random.js';
import type { Rules } from '../src/config/rules.js';
import { simulate } from '../src/simulation/match.js';
import { AIService, DICE_PROBABILITIES } from '../src/ai/AIService.js';

function fixture(rules: Partial<Rules> = {}) {
  const values: number[] = [];
  const engine = new GameEngine('test', GameMode.ONE_VS_ONE, {
    rules: { pressureStartsAt: 10000, ...rules },
    random: () => values.shift() ?? 0,
  });
  engine.addPlayer({ id: 'a', nickname: 'A' });
  engine.addPlayer({ id: 'b', nickname: 'B' });
  engine.startGame();
  const roll = (first = 1, second = 1) => {
    values.push((first - 0.5) / 6, (second - 0.5) / 6);
    engine.dispatch(engine.getSnapshot().currentTurnPlayerId!, { type: 'ROLL' });
  };
  const end = () =>
    engine.dispatch(engine.getSnapshot().currentTurnPlayerId!, { type: 'END_TURN' });
  const player = (id = 'a') => engine.getSnapshot().players.find((p) => p.id === id)!;
  return { engine, roll, end, player };
}

describe('GameEngine authoritative rules', () => {
  it('generates two dice in 1..6 across seeded games', () => {
    const results = new Set<number>();
    for (let seed = 0; seed < 100; seed++) {
      const e = new GameEngine('dice', GameMode.ONE_VS_ONE, { random: seededRandom(seed) });
      e.addPlayer({ id: 'a', nickname: 'A' });
      e.addPlayer({ id: 'b', nickname: 'B' });
      e.startGame();
      e.dispatch('a', { type: 'ROLL' });
      for (const d of e.getSnapshot().gameState.dice!) {
        expect(d).toBeGreaterThanOrEqual(1);
        expect(d).toBeLessThanOrEqual(6);
        results.add(d);
      }
    }
    expect(results.size).toBe(6);
  });
  it('moves by the sum and prevents a second roll or wrong-player action', () => {
    const { engine, roll, player } = fixture();
    expect(() => engine.dispatch('b', { type: 'ROLL' })).toThrow();
    expect(() => engine.dispatch('a', { type: 'END_TURN' })).toThrow();
    roll(2, 3);
    expect(player().position).toBe(5);
    expect(() => engine.dispatch('a', { type: 'ROLL' })).toThrow();
  });
  it('pays start bonus on wraparound exactly once', () => {
    const { roll, end, player } = fixture({ eventAmounts: [0] });
    roll(6, 6);
    end();
    roll();
    end(); // A at 12
    roll(5, 6);
    end();
    roll();
    end(); // A at 23
    roll(5, 6);
    expect(player().position).toBe(2);
    expect(player().money).toBe(1780);
  });
  it('purchases only the landed unowned city and deducts exact price', () => {
    const { engine, roll, player } = fixture();
    roll();
    const tile = engine.getSnapshot().gameState.tiles[2]!;
    engine.dispatch('a', { type: 'BUY' });
    expect(player().money).toBe(1600 - tile.purchasePrice);
    expect(player().ownedTileIds).toEqual([tile.id]);
    expect(engine.getSnapshot().gameState.tiles[2]!.ownerId).toBe('a');
    expect(() => engine.dispatch('a', { type: 'BUY' })).toThrow();
  });
  it('rejects unaffordable voluntary purchases without state change', () => {
    const { engine, roll } = fixture({ startingMoney: 200 });
    roll();
    const before = engine.getSnapshot();
    expect(() => engine.dispatch('a', { type: 'BUY' })).toThrow();
    expect(engine.getSnapshot()).toEqual(before);
  });
  it('transfers only the correct toll between players', () => {
    const { engine, roll, end, player } = fixture();
    roll();
    engine.dispatch('a', { type: 'BUY' });
    const before = player().money;
    const toll = engine.getSnapshot().gameState.tiles[2]!.baseToll;
    end();
    roll();
    expect(player().money).toBe(before + toll);
    expect(player('b').money).toBe(1600 - toll);
  });
  it('upgrades once per turn through level three landmark', () => {
    const { engine, roll, end } = fixture({ startingMoney: 10000, eventAmounts: [0] });
    roll();
    engine.dispatch('a', { type: 'BUY' });
    for (let level = 1; level <= 3; level++) {
      const cost = engine.getActionOptions('a').upgradePrice;
      const before = engine.getSnapshot().players[0]!.money;
      engine.dispatch('a', { type: 'UPGRADE' });
      expect(engine.getSnapshot().gameState.tiles[2]!.buildingLevel).toBe(level);
      expect(engine.getSnapshot().players[0]!.money).toBe(before - cost);
      expect(() => engine.dispatch('a', { type: 'UPGRADE' })).toThrow();
      if (level < 3) {
        end();
        roll(6, 5);
        end();
        roll(6, 6);
        end();
        roll(6, 5);
        end(); // A: 14
        roll(6, 6);
        end();
        roll(6, 5);
        end(); // A: 26
        roll(4, 4); // 2
        // B avoids the rest tile so this scenario isolates the building cap.
      }
    }
    expect(engine.getActionOptions('a').canUpgrade).toBe(false);
  });
  it('bankrupts on event debt, returns properties and finishes game', () => {
    const { engine, roll, end, player } = fixture({ eventAmounts: [-100000] });
    roll();
    engine.dispatch('a', { type: 'BUY' });
    end();
    roll(2, 3);
    end();
    roll();
    expect(player().isBankrupt).toBe(true);
    expect(player().money).toBe(0);
    expect(player().ownedTileIds).toEqual([]);
    expect(engine.getSnapshot().gameState.tiles[2]!.ownerId).toBeNull();
    expect(engine.getSnapshot().status).toBe('FINISHED');
    expect(engine.getSnapshot().gameState.winnerIds).toEqual(['b']);
    expect(() => engine.dispatch('b', { type: 'ROLL' })).toThrow();
  });
  it('handles exact-zero payment as bankruptcy', () => {
    const { engine, roll } = fixture({ startingMoney: 140, eventAmounts: [-140] });
    roll(2, 2);
    expect(engine.getSnapshot().players[0]!.isBankrupt).toBe(true);
  });
  it('credits only available cash when a toll exceeds the payer balance', () => {
    const { engine, roll, end, player } = fixture({
      startingMoney: 400,
      tollMultipliers: [1, 20, 30, 40],
    });
    roll();
    engine.dispatch('a', { type: 'BUY' });
    engine.dispatch('a', { type: 'UPGRADE' });
    const before = player().money;
    end();
    roll();
    expect(player('b').isBankrupt).toBe(true);
    expect(player().money).toBe(before + 400);
    expect(engine.getSnapshot().gameState.winnerIds).toEqual(['a']);
  });
  it('exempts teammates from toll and awards the surviving team', () => {
    const rolls: number[] = [];
    const engine = new GameEngine('teams', GameMode.TWO_VS_TWO, {
      random: () => rolls.shift() ?? 0,
      rules: { eventAmounts: [-100000] },
    });
    for (const [id, teamId] of [
      ['a', 'sun'],
      ['b', 'sun'],
      ['c', 'moon'],
      ['d', 'moon'],
    ])
      engine.addPlayer({ id: id!, nickname: id!, teamId: teamId! });
    engine.startGame();
    engine.dispatch('a', { type: 'ROLL' });
    engine.dispatch('a', { type: 'BUY' });
    engine.dispatch('a', { type: 'END_TURN' });
    engine.dispatch('b', { type: 'ROLL' });
    expect(engine.getSnapshot().players[1]!.money).toBe(1600);
    engine.dispatch('b', { type: 'END_TURN' });
    for (const id of ['c', 'd']) {
      rolls.push(0.2, 0.2);
      engine.dispatch(id, { type: 'ROLL' });
    }
    expect(engine.getSnapshot().status).toBe('FINISHED');
    expect(engine.getSnapshot().gameState.winnerIds).toEqual(['a', 'b']);
  });
  it('travels forward to START and awards one bonus', () => {
    const { roll, end, player } = fixture({ eventAmounts: [0] });
    roll(6, 6);
    end();
    roll();
    end();
    roll(2, 2);
    expect(player().position).toBe(0);
    expect(player().money).toBe(1780);
  });
  it('skips one next turn on rest tile', () => {
    const { engine, roll, end, player } = fixture();
    roll(4, 4);
    end();
    roll();
    end();
    expect(engine.getSnapshot().currentTurnPlayerId).toBe('b');
    expect(player().skipTurns).toBe(0);
  });
  it('does not expose mutable internal state', () => {
    const { engine } = fixture();
    const copy = engine.getSnapshot();
    copy.players[0]!.money = -999;
    expect(engine.getSnapshot().players[0]!.money).toBe(1600);
  });
  it('validates player count and teams', () => {
    const e = new GameEngine('team', GameMode.TWO_VS_TWO);
    e.addPlayer({ id: 'a', nickname: 'A' });
    expect(() => e.addPlayer({ id: 'a', nickname: 'B' })).toThrow();
    expect(() => e.startGame()).toThrow();
    for (const id of ['b', 'c', 'd']) e.addPlayer({ id, nickname: id });
    expect(() => e.startGame()).toThrow();
    expect(() => e.addPlayer({ id: 'e', nickname: 'E' })).toThrow();
  });
  it('supports injected victory conditions', () => {
    const e = new GameEngine('custom', GameMode.ONE_VS_ONE, {
      random: () => 0,
      victoryConditions: [
        { evaluate: (room) => (room.players[0]!.ownedTileIds.length ? ['a'] : null) },
      ],
    });
    e.addPlayer({ id: 'a', nickname: 'A' });
    e.addPlayer({ id: 'b', nickname: 'B' });
    e.startGame();
    e.dispatch('a', { type: 'ROLL' });
    e.dispatch('a', { type: 'BUY' });
    expect(e.getSnapshot().gameState.winnerIds).toEqual(['a']);
  });
});

describe('AI simulations', () => {
  it('preserves a cash reserve', () => {
    const { engine, roll } = fixture({ startingMoney: 300 });
    roll();
    expect(new AIService().decide(engine.getSnapshot(), engine.getActionOptions('a'))).toEqual({
      type: 'END_TURN',
    });
  });
  it('dice distribution sums to one', () => {
    expect(Object.values(DICE_PROBABILITIES).reduce((a, b) => a + b, 0)).toBeCloseTo(1);
  });
  for (const difficulty of Object.values(AIDifficulty))
    for (const count of [2, 4]) {
      it(`${difficulty}: ${count} AI players finish across 20 seeds with coherent ownership`, () => {
        for (let seed = 0; seed < 20; seed++) {
          const room = simulate(count, seed, undefined, difficulty);
          expect(room.status).toBe('FINISHED');
          expect(room.gameState.winnerIds).toHaveLength(1);
          expect(room.players.filter((p) => !p.isBankrupt)).toHaveLength(1);
          for (const player of room.players) {
            expect(player.money).toBeGreaterThanOrEqual(0);
            expect(player.ownedTileIds.sort()).toEqual(
              room.gameState.tiles
                .filter((t) => t.ownerId === player.id)
                .map((t) => t.id)
                .sort(),
            );
          }
        }
      }, 20000);
    }
  it('replays deterministically', () => {
    expect(simulate(4, 77)).toEqual(simulate(4, 77));
  });
  it('reports an unfinished simulation as failure', () => {
    expect(() => simulate(4, 1, undefined, AIDifficulty.NORMAL, 1)).toThrow('시뮬레이션 실패');
  });
});
