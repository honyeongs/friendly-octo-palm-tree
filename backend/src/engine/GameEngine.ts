import { randomInt } from 'node:crypto';
import {
  AIDifficulty,
  GameMode,
  type ActionOptions,
  type GameAction,
  type GameLog,
  type GameRoom,
  type Player,
  type PlayerInput,
  type Tile,
} from '../../../shared/src/index.js';
import { createBoard } from '../config/board.js';
import { DEFAULT_RULES, type Rules } from '../config/rules.js';
import type { RandomSource } from './random.js';
import { LastStandingVictory, type VictoryCondition } from './victory.js';

export class GameRuleError extends Error {}
export class GameTurnLimitError extends Error {
  constructor(readonly maxTurns: number) {
    super(`최대 ${maxTurns}턴에 도달했습니다.`);
  }
}
export interface EngineOptions {
  rules?: Partial<Rules>;
  random?: RandomSource;
  victoryConditions?: VictoryCondition[];
  maxTurns?: number;
}

export class GameEngine {
  private room: GameRoom;
  readonly rules: Readonly<Rules>;
  private readonly random: RandomSource;
  private readonly victories: VictoryCondition[];
  private sequence = 0;
  private readonly maxTurns: number;
  constructor(roomId: string, mode: GameMode = GameMode.SOLO_AI, options: EngineOptions = {}) {
    this.maxTurns = options.maxTurns ?? Number.MAX_SAFE_INTEGER;
    this.require(
      Number.isSafeInteger(this.maxTurns) && this.maxTurns > 0,
      '최대 턴은 양의 정수여야 합니다.',
    );
    const rules = { ...DEFAULT_RULES, ...options.rules };
    this.rules = Object.freeze({
      ...rules,
      upgradePriceRatios: Object.freeze([...rules.upgradePriceRatios]),
      tollMultipliers: Object.freeze([...rules.tollMultipliers]),
      eventAmounts: Object.freeze([...rules.eventAmounts]),
    });
    this.validateRules();
    this.random = options.random ?? (() => randomInt(0, 0x100000000) / 0x100000000);
    this.victories = [...(options.victoryConditions ?? []), new LastStandingVictory()];
    this.room = {
      roomId,
      mode,
      players: [],
      currentTurnPlayerId: null,
      turnNumber: 0,
      status: 'WAITING',
      gameState: {
        tiles: createBoard(),
        phase: 'WAITING',
        dice: null,
        lastRoll: null,
        winnerIds: [],
        bankruptcyOrder: [],
        logs: [],
        hasBuiltThisTurn: false,
        revision: 0,
      },
    };
  }
  // Callers only receive copies: neither sockets nor AI can mutate authoritative state.
  getSnapshot(): GameRoom {
    return structuredClone(this.room);
  }
  addPlayer(input: PlayerInput): void {
    this.require(this.room.status === 'WAITING', '이미 시작한 게임입니다.');
    this.require(this.room.players.length < this.rules.maxPlayers, '방이 가득 찼습니다.');
    this.require(
      input.id.length > 0 && !this.room.players.some((p) => p.id === input.id),
      '중복되거나 빈 플레이어 ID입니다.',
    );
    const nickname = input.nickname.trim();
    this.require(nickname.length > 0 && nickname.length <= 20, '닉네임은 1~20자여야 합니다.');
    this.room.players.push({
      id: input.id,
      nickname,
      money: this.rules.startingMoney,
      position: 0,
      ownedTileIds: [],
      isAI: input.isAI ?? false,
      teamId: input.teamId ?? null,
      isBankrupt: false,
      rp: 1000,
      skipTurns: 0,
      difficulty: input.difficulty ?? AIDifficulty.NORMAL,
    });
    this.room.gameState.revision++;
  }
  startGame(): void {
    this.require(this.room.status === 'WAITING', '게임은 한 번만 시작할 수 있습니다.');
    const { players, mode } = this.room;
    this.require(players.length >= 2, '최소 2명이 필요합니다.');
    if (mode === GameMode.ONE_VS_ONE)
      this.require(players.length === 2, '1vs1은 2명이 필요합니다.');
    if (mode === GameMode.FOUR_PLAYER_FFA || mode === GameMode.TWO_VS_TWO)
      this.require(players.length === 4, '이 모드는 4명이 필요합니다.');
    if (mode === GameMode.TWO_VS_TWO) {
      const teams = new Set(players.map((p) => p.teamId));
      this.require(
        !teams.has(null) &&
          teams.size === 2 &&
          [...teams].every((team) => players.filter((p) => p.teamId === team).length === 2),
        '2vs2는 각 2명인 두 팀이 필요합니다.',
      );
    }
    this.room.status = 'PLAYING';
    this.room.turnNumber = 1;
    this.room.currentTurnPlayerId = players[0]!.id;
    this.room.gameState.phase = 'AWAIT_ROLL';
    this.log('별길 상회 거래 시작');
    this.log(`Turn 1 · ${players[0]!.nickname}`);
    this.room.gameState.revision++;
  }
  dispatch(playerId: string, action: GameAction): GameLog[] {
    this.require(this.room.status === 'PLAYING', '진행 중인 게임이 아닙니다.');
    this.require(
      playerId === this.room.currentTurnPlayerId,
      '현재 턴의 플레이어만 행동할 수 있습니다.',
    );
    const player = this.player(playerId);
    this.require(!player.isBankrupt, '파산한 플레이어입니다.');
    const before = this.sequence;
    const options = this.getActionOptions(playerId);
    try {
      switch (action.type) {
        case 'ROLL':
          this.require(options.canRoll, '지금은 주사위를 굴릴 수 없습니다.');
          this.rollDice(player);
          break;
        case 'BUY':
          this.require(options.canBuy, '구매할 수 없습니다.');
          this.buyProperty(player);
          break;
        case 'UPGRADE':
          this.require(options.canUpgrade, '업그레이드할 수 없습니다.');
          this.upgradeProperty(player);
          break;
        case 'END_TURN':
          this.require(options.canEndTurn, '먼저 주사위를 굴리세요.');
          this.nextTurn();
          break;
        default:
          throw new GameRuleError('알 수 없는 행동입니다.');
      }
    } catch (error) {
      // The simulation cap can stop after a rest/upkeep transition. Publish a new
      // revision for that final snapshot; rejected game actions remain unchanged.
      if (error instanceof GameTurnLimitError) this.room.gameState.revision++;
      throw error;
    }
    this.room.gameState.revision++;
    return structuredClone(this.room.gameState.logs.filter((log) => log.sequence > before));
  }
  getActionOptions(playerId: string): ActionOptions {
    const player = this.room.players.find((p) => p.id === playerId);
    const tile = player ? this.room.gameState.tiles[player.position] : undefined;
    const current =
      this.room.status === 'PLAYING' &&
      this.room.currentTurnPlayerId === playerId &&
      !!player &&
      !player.isBankrupt;
    const canAct = current && this.room.gameState.phase === 'AWAIT_ACTION';
    const upgradePrice = tile ? this.upgradeCost(tile) : 0;
    return {
      canRoll: current && this.room.gameState.phase === 'AWAIT_ROLL',
      canBuy:
        canAct &&
        tile?.type === 'CITY' &&
        tile.ownerId === null &&
        player!.money > tile.purchasePrice,
      canUpgrade:
        canAct &&
        tile?.type === 'CITY' &&
        tile.ownerId === playerId &&
        tile.buildingLevel < this.rules.upgradePriceRatios.length &&
        !this.room.gameState.hasBuiltThisTurn &&
        player!.money > upgradePrice,
      canEndTurn: canAct,
      upgradePrice,
      toll: tile ? this.toll(tile) : 0,
    };
  }
  private rollDice(player: Player): void {
    const from = player.position;
    // Sample both dice before mutating state, so an invalid RNG cannot leave a partial roll.
    const dice: [number, number] = [this.sample(6) + 1, this.sample(6) + 1];
    this.room.gameState.dice = dice;
    this.room.gameState.phase = 'AWAIT_ACTION';
    this.log(`${player.nickname} rolled ${dice[0]} + ${dice[1]}`);
    this.movePlayer(player, dice[0] + dice[1]);
    this.resolveTile(player);
    // Retain the resolved roll even if bankruptcy immediately advances and clears turn dice.
    this.room.gameState.lastRoll = {
      playerId: player.id,
      dice,
      from,
      to: player.position,
      tileId: this.room.gameState.tiles[player.position]!.id,
    };
    this.checkWinner();
    if (player.isBankrupt && this.room.status === 'PLAYING') this.nextTurn();
  }
  private movePlayer(player: Player, steps: number): void {
    const from = player.position;
    const total = from + steps;
    const size = this.room.gameState.tiles.length;
    const laps = Math.floor(total / size);
    player.position = total % size;
    this.log(`${player.nickname} moved from ${from} to ${player.position}`);
    if (laps > 0) {
      player.money += laps * this.rules.startBonus;
      this.log(
        `${player.nickname} passed START +${laps * this.rules.startBonus} · Remaining money: ${player.money}`,
      );
    }
  }
  private resolveTile(player: Player, depth = 0): void {
    this.require(depth < this.room.gameState.tiles.length, '이동 타일 순환을 감지했습니다.');
    const tile = this.room.gameState.tiles[player.position]!;
    if (tile.type === 'CITY') this.payToll(player, tile);
    const effect = tile.specialEffect;
    if (effect?.kind === 'EVENT') {
      const amount = this.rules.eventAmounts[this.sample(this.rules.eventAmounts.length)]!;
      if (amount < 0) this.pay(player, -amount, null, '바람 소식');
      else {
        player.money += amount;
        this.log(`${player.nickname} event +${amount} · Remaining money: ${player.money}`);
      }
    } else if (effect?.kind === 'REST') {
      player.skipTurns = effect.turns;
      this.log(`${player.nickname} 안개 쉼터: 다음 ${effect.turns}턴 휴식`);
    } else if (effect?.kind === 'TRAVEL') {
      const size = this.room.gameState.tiles.length;
      this.movePlayer(player, (effect.destination - player.position + size) % size);
      this.resolveTile(player, depth + 1);
    }
  }
  private buyProperty(player: Player): void {
    const tile = this.room.gameState.tiles[player.position]!;
    player.money -= tile.purchasePrice;
    player.ownedTileIds.push(tile.id);
    tile.ownerId = player.id;
    this.log(
      `${player.nickname} purchased ${tile.name} for ${tile.purchasePrice} · Remaining money: ${player.money}`,
    );
    this.checkWinner();
  }
  private upgradeProperty(player: Player): void {
    const tile = this.room.gameState.tiles[player.position]!;
    const price = this.upgradeCost(tile);
    player.money -= price;
    tile.buildingLevel++;
    this.room.gameState.hasBuiltThisTurn = true;
    this.log(
      `${player.nickname} upgraded ${tile.name} to ${tile.buildingLevel === 3 ? 'LANDMARK' : `level ${tile.buildingLevel}`} for ${price} · Remaining money: ${player.money}`,
    );
    this.checkWinner();
  }
  private payToll(player: Player, tile: Tile): void {
    if (!tile.ownerId || tile.ownerId === player.id) return;
    const owner = this.player(tile.ownerId);
    const teammate = this.room.mode === GameMode.TWO_VS_TWO && player.teamId === owner.teamId;
    if (!owner.isBankrupt && !teammate)
      this.pay(player, this.toll(tile), owner, `${tile.name} toll`);
  }
  private pay(player: Player, amount: number, recipient: Player | null, reason: string): void {
    // No borrowing or forced asset sale in this ruleset. Credit only the cash actually paid.
    const paid = Math.min(player.money, amount);
    player.money -= paid;
    if (recipient) recipient.money += paid;
    this.log(
      `${player.nickname} paid ${paid}/${amount} for ${reason}${recipient ? ` to ${recipient.nickname}` : ''} · Remaining money: ${player.money}`,
    );
    this.handleBankruptcy(player);
  }
  private handleBankruptcy(player: Player): void {
    if (player.money <= 0 && !player.isBankrupt) {
      player.isBankrupt = true;
      // Keep authoritative history separate from the bounded display log.
      this.room.gameState.bankruptcyOrder.push(player.id);
      for (const tile of this.room.gameState.tiles)
        if (tile.ownerId === player.id) {
          tile.ownerId = null;
          tile.buildingLevel = 0;
        }
      player.ownedTileIds = [];
      this.log(`${player.nickname} BANKRUPT · 보유 도시는 은행으로 반환`);
    }
  }
  private nextTurn(): void {
    this.checkWinner();
    if (this.room.status !== 'PLAYING') return;
    let index = this.room.players.findIndex((p) => p.id === this.room.currentTurnPlayerId);
    // Iterative turn selection handles bankrupt/resting players without recursion.
    while (this.room.status === 'PLAYING') {
      index = (index + 1) % this.room.players.length;
      const next = this.room.players[index]!;
      if (next.isBankrupt) continue;
      // Check inside the loop: resting and upkeep-bankrupt players also consume turns.
      if (this.room.turnNumber >= this.maxTurns) throw new GameTurnLimitError(this.maxTurns);
      this.room.turnNumber++;
      this.room.currentTurnPlayerId = next.id;
      this.room.gameState.dice = null;
      this.room.gameState.hasBuiltThisTurn = false;
      this.log(`Turn ${this.room.turnNumber} · ${next.nickname}`);
      const upkeep = this.pressure() * this.rules.upkeepPerPressure;
      if (upkeep > 0) {
        this.pay(next, upkeep, null, '항로 유지비');
        this.checkWinner();
      }
      if (this.room.status !== 'PLAYING') return;
      if (next.isBankrupt) continue;
      if (next.skipTurns > 0) {
        next.skipTurns--;
        this.log(`${next.nickname} rests this turn`);
        continue;
      }
      this.room.gameState.phase = 'AWAIT_ROLL';
      return;
    }
  }
  private checkWinner(): void {
    for (const condition of this.victories) {
      const winnerIds = condition.evaluate(this.getSnapshot());
      if (winnerIds) {
        this.room.status = 'FINISHED';
        this.room.gameState.phase = 'FINISHED';
        this.room.gameState.winnerIds = winnerIds;
        this.log(`WINNER: ${winnerIds.map((id) => this.player(id).nickname).join(', ')}`);
        return;
      }
    }
  }
  private pressure(): number {
    return this.room.turnNumber < this.rules.pressureStartsAt
      ? 0
      : 1 +
          Math.floor(
            (this.room.turnNumber - this.rules.pressureStartsAt) / this.rules.pressureInterval,
          );
  }
  private toll(tile: Tile): number {
    return Math.ceil(
      tile.baseToll *
        (this.rules.tollMultipliers[tile.buildingLevel] ?? 1) *
        (1 + this.pressure() * this.rules.pressureTollIncrement),
    );
  }
  private upgradeCost(tile: Tile): number {
    return Math.ceil(tile.purchasePrice * (this.rules.upgradePriceRatios[tile.buildingLevel] ?? 0));
  }
  private player(id: string): Player {
    const p = this.room.players.find((p) => p.id === id);
    this.require(p, '플레이어를 찾을 수 없습니다.');
    return p;
  }
  private sample(size: number): number {
    const value = this.random();
    this.require(
      Number.isFinite(value) && value >= 0 && value < 1,
      '난수는 [0, 1) 범위여야 합니다.',
    );
    return Math.floor(value * size);
  }
  private log(message: string): void {
    this.room.gameState.logs.push({
      sequence: ++this.sequence,
      turn: this.room.turnNumber,
      message,
    });
    if (this.room.gameState.logs.length > this.rules.maxLogs) this.room.gameState.logs.shift();
  }
  private require(condition: unknown, message: string): asserts condition {
    if (!condition) throw new GameRuleError(message);
  }
  private validateRules(): void {
    const r = this.rules;
    for (const value of [r.startingMoney, r.pressureInterval, r.maxLogs])
      this.require(Number.isSafeInteger(value) && value > 0, '양의 정수 규칙이 필요합니다.');
    this.require(
      Number.isInteger(r.maxPlayers) && r.maxPlayers >= 2 && r.maxPlayers <= 4,
      '최대 인원은 2~4명입니다.',
    );
    for (const value of [r.startBonus, r.pressureStartsAt, r.upkeepPerPressure])
      this.require(
        Number.isSafeInteger(value) && value >= 0,
        '음수가 아닌 정수 규칙이 필요합니다.',
      );
    this.require(
      Number.isFinite(r.pressureTollIncrement) && r.pressureTollIncrement >= 0,
      '유효하지 않은 통행료 상승률입니다.',
    );
    this.require(
      r.upgradePriceRatios.length === 3 &&
        r.tollMultipliers.length === 4 &&
        [...r.upgradePriceRatios, ...r.tollMultipliers].every((v) => Number.isFinite(v) && v > 0),
      '건물은 3단계와 기본 통행료 배율이 필요합니다.',
    );
    this.require(
      r.eventAmounts.length > 0 && r.eventAmounts.every(Number.isSafeInteger),
      '이벤트 금액이 유효하지 않습니다.',
    );
  }
}
