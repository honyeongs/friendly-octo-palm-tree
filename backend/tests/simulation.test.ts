import { describe, expect, it } from 'vitest';
import { AIDifficulty, GameMode } from '../../shared/src/index.js';
import { GameEngine, GameTurnLimitError } from '../src/engine/GameEngine.js';
import { createSimulation, simulate, SimulationLimitError } from '../src/simulation/match.js';
import { formatSummary, summarize } from '../src/simulation/report.js';

describe('standalone simulation and authoritative history', () => {
  it('creates four AI players by default using the same action interface', () => {
    const { engine, ai } = createSimulation();
    const before = engine.getSnapshot();
    expect(before.players).toHaveLength(4);
    expect(before.players.every((p) => p.isAI)).toBe(true);
    const id = before.currentTurnPlayerId!;
    const action = ai.decide(before, engine.getActionOptions(id));
    expect(action).toEqual({ type: 'ROLL' });
    expect(engine.getSnapshot()).toEqual(before);
    engine.dispatch(id, action);
    expect(engine.getSnapshot().gameState.revision).toBe(before.gameState.revision + 1);
  });

  it('reports winner, total turns, final balances, cities, and ordered bankruptcies', () => {
    const room = simulate();
    const summary = summarize(room);
    expect(summary.winners).toEqual(['AI_3']);
    expect(summary.totalTurns).toBe(136);
    expect(summary.players).toHaveLength(4);
    expect(summary.bankruptcyOrder).toHaveLength(3);
    expect(new Set(summary.bankruptcyOrder).size).toBe(3);
    for (const result of summary.players) {
      const player = room.players.find((p) => p.id === result.id)!;
      expect(result.money).toBe(player.money);
      expect(result.ownedCities).toEqual(
        room.gameState.tiles.filter((t) => player.ownedTileIds.includes(t.id)).map((t) => t.name),
      );
      if (result.isBankrupt) expect(result.ownedCities).toEqual([]);
    }
    const text = formatSummary(room);
    for (const field of ['승자: AI_3', '총 턴 수: 136', '최종 자금:', '소유 도시:', '파산 순서:'])
      expect(text).toContain(field);
  });

  it('retains exact bankruptcy order even after display logs are trimmed', () => {
    const engine = new GameEngine('history', GameMode.FOUR_PLAYER_FFA, {
      random: () => 0.2,
      rules: { startingMoney: 100, eventAmounts: [-100], maxLogs: 1 },
    });
    for (const id of ['a', 'b', 'c', 'd']) engine.addPlayer({ id, nickname: id });
    engine.startGame();
    for (const id of ['a', 'b', 'c']) engine.dispatch(id, { type: 'ROLL' });
    const room = engine.getSnapshot();
    expect(room.gameState.logs).toHaveLength(1);
    expect(room.gameState.bankruptcyOrder).toEqual(['a', 'b', 'c']);
    expect(room.gameState.winnerIds).toEqual(['d']);
    room.gameState.bankruptcyOrder.reverse();
    room.players[3]!.ownedTileIds.push('fake-city');
    room.gameState.tiles[1]!.ownerId = 'd';
    expect(engine.getSnapshot().gameState.bankruptcyOrder).toEqual(['a', 'b', 'c']);
    expect(engine.getSnapshot().players[3]!.ownedTileIds).toEqual([]);
    expect(engine.getSnapshot().gameState.tiles[1]!.ownerId).toBeNull();
  });

  it('stops at the maximum turn without declaring a fake winner', () => {
    try {
      simulate(4, 42, undefined, AIDifficulty.NORMAL, 20000, 1);
      expect.fail('Expected maximum-turn termination');
    } catch (error) {
      expect(error).toBeInstanceOf(SimulationLimitError);
      if (!(error instanceof SimulationLimitError)) throw error;
      expect(error.reason).toBe('MAX_TURNS');
      expect(error.room.turnNumber).toBe(1);
      expect(error.room.status).toBe('PLAYING');
      expect(error.room.gameState.winnerIds).toEqual([]);
      expect(formatSummary(error.room, error.reason)).toContain('승자: 없음 (미종료)');
    }
  });

  it('enforces the limit inside a transition that skips resting players', () => {
    const values = [0.55, 0.55, 0, 0]; // A rests at 8; B lands at 2.
    const engine = new GameEngine('rest-limit', GameMode.ONE_VS_ONE, {
      random: () => values.shift() ?? 0,
      maxTurns: 3,
    });
    for (const id of ['a', 'b']) engine.addPlayer({ id, nickname: id });
    engine.startGame();
    engine.dispatch('a', { type: 'ROLL' });
    engine.dispatch('a', { type: 'END_TURN' });
    engine.dispatch('b', { type: 'ROLL' });
    const revision = engine.getSnapshot().gameState.revision;
    expect(() => engine.dispatch('b', { type: 'END_TURN' })).toThrow(GameTurnLimitError);
    expect(engine.getSnapshot().turnNumber).toBe(3);
    expect(engine.getSnapshot().gameState.revision).toBe(revision + 1);
    expect(engine.getSnapshot().players[0]!.skipTurns).toBe(0);
  });

  it('allows a genuine victory on the last permitted turn', () => {
    const engine = new GameEngine('last-turn', GameMode.ONE_VS_ONE, {
      maxTurns: 1,
      random: () => 0.2,
      rules: { eventAmounts: [-10000] },
    });
    for (const id of ['a', 'b']) engine.addPlayer({ id, nickname: id });
    engine.startGame();
    engine.dispatch('a', { type: 'ROLL' });
    expect(engine.getSnapshot().status).toBe('FINISHED');
    expect(engine.getSnapshot().gameState.winnerIds).toEqual(['b']);
  });

  it('keeps an action limit as an independent safeguard', () => {
    try {
      simulate(4, 42, undefined, AIDifficulty.NORMAL, 1);
      expect.fail('Expected action limit');
    } catch (error) {
      expect(error).toBeInstanceOf(SimulationLimitError);
      if (!(error instanceof SimulationLimitError)) throw error;
      expect(error.reason).toBe('MAX_ACTIONS');
    }
  });

  it('accepts completion on exactly the last permitted action', () => {
    const { engine, ai } = createSimulation();
    let actions = 0;
    while (engine.getSnapshot().status === 'PLAYING' && actions < 20000) {
      const room = engine.getSnapshot();
      const id = room.currentTurnPlayerId!;
      engine.dispatch(id, ai.decide(room, engine.getActionOptions(id)));
      actions++;
    }
    expect(simulate(4, 42, undefined, AIDifficulty.NORMAL, actions).status).toBe('FINISHED');
  });

  it.each([0, -1, 1.5, NaN, Infinity])('rejects invalid limits: %s', (value) => {
    expect(() => simulate(4, 42, undefined, AIDifficulty.NORMAL, 20000, value)).toThrow();
    expect(() => simulate(4, 42, undefined, AIDifficulty.NORMAL, value)).toThrow();
  });
});
