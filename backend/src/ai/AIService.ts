import {
  AIDifficulty,
  GameMode,
  type ActionOptions,
  type GameAction,
  type GameRoom,
  type Player,
  type Tile,
} from '../../../shared/src/index.js';
import type { RandomSource } from '../engine/random.js';
import { AI_CONFIG } from '../config/ai.js';

export interface AIContext {
  room: GameRoom;
  player: Player;
  tile: Tile;
  options: ActionOptions;
}
export interface StrategyEvaluator {
  reserve(context: AIContext): number;
  scorePurchase(context: AIContext): number;
  scoreUpgrade(context: AIContext): number;
}
export class NormalEvaluator implements StrategyEvaluator {
  reserve({ player }: AIContext): number {
    return Math.max(AI_CONFIG.minimumReserve, Math.floor(player.money * AI_CONFIG.reserveRatio));
  }
  scorePurchase({ room, player, tile }: AIContext): number {
    const district = room.gameState.tiles.filter(
      (t) => t.groupId === tile.groupId && t.type === 'CITY',
    );
    const held = district.filter((t) => t.ownerId === player.id).length;
    return (
      tile.baseToll / tile.purchasePrice +
      (held / Math.max(1, district.length)) * AI_CONFIG.districtWeight
    );
  }
  scoreUpgrade({ tile, options }: AIContext): number {
    return options.toll / Math.max(1, options.upgradePrice);
  }
}
// Exact two-dice sum distribution. Future strategies can add multi-turn path/event models.
export const DICE_PROBABILITIES: Readonly<Record<number, number>> = Object.freeze({
  2: 1 / 36,
  3: 2 / 36,
  4: 3 / 36,
  5: 4 / 36,
  6: 5 / 36,
  7: 6 / 36,
  8: 5 / 36,
  9: 4 / 36,
  10: 3 / 36,
  11: 2 / 36,
  12: 1 / 36,
});
export class HardEvaluator extends NormalEvaluator {
  private traffic({ room, player, tile }: AIContext): number {
    return room.players
      .filter(
        (p) =>
          p.id !== player.id &&
          !p.isBankrupt &&
          p.skipTurns === 0 &&
          !(room.mode === GameMode.TWO_VS_TWO && p.teamId === player.teamId),
      )
      .reduce(
        (sum, p) =>
          sum +
          (DICE_PROBABILITIES[
            (tile.index - p.position + room.gameState.tiles.length) % room.gameState.tiles.length
          ] ?? 0),
        0,
      );
  }
  override scorePurchase(context: AIContext): number {
    return super.scorePurchase(context) + this.traffic(context);
  }
  override scoreUpgrade(context: AIContext): number {
    return super.scoreUpgrade(context) + this.traffic(context) * AI_CONFIG.hardUpgradeTrafficWeight;
  }
}
export class AIService {
  constructor(
    private readonly random: RandomSource = Math.random,
    private readonly evaluators: Partial<Record<AIDifficulty, StrategyEvaluator>> = {},
  ) {}
  // Human, AI, and future remote controllers all produce the same GameAction contract.
  decide(room: GameRoom, options: ActionOptions): GameAction {
    const player = room.players.find((p) => p.id === room.currentTurnPlayerId);
    if (!player || room.status !== 'PLAYING')
      throw new Error('AI가 행동할 진행 중인 턴이 없습니다.');
    if (options.canRoll) return { type: 'ROLL' };
    if (!options.canEndTurn) throw new Error('AI가 선택할 수 있는 행동이 없습니다.');
    const tile = room.gameState.tiles[player.position]!;
    const context: AIContext = { room, player, tile, options };
    const evaluator =
      this.evaluators[player.difficulty] ??
      (player.difficulty === AIDifficulty.HARD ? new HardEvaluator() : new NormalEvaluator());
    const reserve = evaluator.reserve(context);
    const willing =
      player.difficulty !== AIDifficulty.EASY || this.random() > AI_CONFIG.easySkipProbability;
    if (
      willing &&
      options.canBuy &&
      player.money - tile.purchasePrice >= reserve &&
      evaluator.scorePurchase(context) >= AI_CONFIG.purchaseThreshold
    )
      return { type: 'BUY' };
    if (
      willing &&
      options.canUpgrade &&
      player.money - options.upgradePrice >= reserve &&
      evaluator.scoreUpgrade(context) >= AI_CONFIG.upgradeThreshold
    )
      return { type: 'UPGRADE' };
    return { type: 'END_TURN' };
  }
}
