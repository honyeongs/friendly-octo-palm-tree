import { AIDifficulty, GameMode, type GameLog, type GameRoom } from '../../../shared/src/index.js';
import { GameEngine, GameTurnLimitError } from '../engine/GameEngine.js';
import { seededRandom } from '../engine/random.js';
import { AIService } from '../ai/AIService.js';
import { SIMULATION_CONFIG } from '../config/simulation.js';

export class SimulationLimitError extends Error {
  constructor(
    readonly room: GameRoom,
    readonly reason: 'MAX_TURNS' | 'MAX_ACTIONS',
  ) {
    super(`시뮬레이션 실패: ${reason} 제한에 도달했습니다 (turn=${room.turnNumber}).`);
  }
}

export function createSimulation(
  count = 4,
  seed = 42,
  difficulty = AIDifficulty.NORMAL,
  maxTurns: number = SIMULATION_CONFIG.maxTurns,
): { engine: GameEngine; ai: AIService } {
  if (count !== 2 && count !== 4) throw new Error('자동 대전 인원은 2 또는 4입니다.');
  const engine = new GameEngine(
    `simulation-${seed}`,
    count === 4 ? GameMode.FOUR_PLAYER_FFA : GameMode.ONE_VS_ONE,
    { random: seededRandom(seed), maxTurns },
  );
  for (let i = 1; i <= count; i++)
    engine.addPlayer({ id: `ai-${i}`, nickname: `AI_${i}`, isAI: true, difficulty });
  engine.startGame();
  return { engine, ai: new AIService(seededRandom(seed + 1000)) };
}
export function simulate(
  count = 4,
  seed = 42,
  onLog: (log: GameLog) => void = () => {},
  difficulty = AIDifficulty.NORMAL,
  maxActions: number = SIMULATION_CONFIG.maxActions,
  maxTurns: number = SIMULATION_CONFIG.maxTurns,
): GameRoom {
  if (!Number.isSafeInteger(maxActions) || maxActions <= 0)
    throw new Error('최대 행동 수는 양의 정수여야 합니다.');
  const { engine, ai } = createSimulation(count, seed, difficulty, maxTurns);
  engine.getSnapshot().gameState.logs.forEach(onLog);
  for (let i = 0; i < maxActions; i++) {
    const room = engine.getSnapshot();
    if (room.status === 'FINISHED') return room;
    const id = room.currentTurnPlayerId!;
    try {
      engine.dispatch(id, ai.decide(room, engine.getActionOptions(id))).forEach(onLog);
    } catch (error) {
      if (!(error instanceof GameTurnLimitError)) throw error;
      const stopped = engine.getSnapshot();
      // A turn transition may have processed a rest/upkeep before reaching the cap.
      const lastSequence = room.gameState.logs.at(-1)?.sequence ?? 0;
      stopped.gameState.logs.filter((log) => log.sequence > lastSequence).forEach(onLog);
      throw new SimulationLimitError(stopped, 'MAX_TURNS');
    }
  }
  const final = engine.getSnapshot();
  if (final.status === 'FINISHED') return final;
  throw new SimulationLimitError(final, 'MAX_ACTIONS');
}
