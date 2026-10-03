import {
  GameMode,
  type GameAction,
  type GameRoom,
  type LobbyRoom,
  type RoomView,
} from '../../../shared/src/index.js';
import { GameEngine, type EngineOptions } from '../engine/GameEngine.js';
import { AIService } from '../ai/AIService.js';
import { SERVER_CONFIG } from '../config/server.js';
export interface MatchChange {
  before: GameRoom;
  after: GameRoom;
  actorId: string;
  action: GameAction;
}
interface Match {
  engine: GameEngine;
  bots: Set<string>;
  paused: boolean;
  timer?: ReturnType<typeof setTimeout>;
}
export class MatchManager {
  private readonly matches = new Map<string, Match>();
  private readonly ai = new AIService();
  constructor(
    private readonly changed: (change: MatchChange) => void,
    private readonly failed: (roomId: string) => void,
    private readonly delay: number = SERVER_CONFIG.aiDelayMs,
    private readonly engineOptions: () => EngineOptions = () => ({}),
  ) {}
  create(room: LobbyRoom): void {
    if (this.matches.has(room.roomId)) throw new Error('이미 시작한 경기입니다.');
    const engine = new GameEngine(room.roomId, room.mode, this.engineOptions());
    room.members.forEach((p, i) =>
      engine.addPlayer({
        id: p.playerId,
        nickname: p.nickname,
        isAI: p.control === 'AI',
        difficulty: p.difficulty,
        teamId: room.mode === GameMode.TWO_VS_TWO ? `team-${i % 2}` : null,
      }),
    );
    engine.startGame();
    this.matches.set(room.roomId, {
      engine,
      bots: new Set(room.members.filter((p) => p.control === 'AI').map((p) => p.playerId)),
      paused: false,
    });
  }
  view(roomId: string, playerId: string): RoomView {
    const match = this.requireMatch(roomId);
    const options = match.engine.getActionOptions(playerId);
    if (match.paused || match.bots.has(playerId)) {
      options.canRoll = false;
      options.canBuy = false;
      options.canUpgrade = false;
      options.canEndTurn = false;
    }
    return { room: match.engine.getSnapshot(), you: playerId, options };
  }
  act(roomId: string, playerId: string, action: GameAction, revision: number): void {
    const match = this.requireMatch(roomId);
    if (match.paused) throw new Error('재접속을 기다리는 동안 경기가 일시정지됩니다.');
    if (match.bots.has(playerId)) throw new Error('AI가 이어받은 플레이어입니다.');
    if (match.engine.getSnapshot().gameState.revision !== revision)
      throw new Error('이전 상태의 요청입니다. 최신 상태에서 다시 시도하세요.');
    this.dispatch(roomId, match, playerId, action);
  }
  sync(room: LobbyRoom): void {
    const match = this.matches.get(room.roomId);
    if (!match) return;
    match.paused = room.paused;
    match.bots = new Set(room.members.filter((p) => p.control === 'AI').map((p) => p.playerId));
    if (match.timer) {
      clearTimeout(match.timer);
      match.timer = undefined;
    }
    this.schedule(room.roomId, match);
  }
  remove(roomId: string): void {
    const m = this.matches.get(roomId);
    if (m?.timer) clearTimeout(m.timer);
    this.matches.delete(roomId);
  }
  close(): void {
    for (const id of this.matches.keys()) this.remove(id);
  }
  private dispatch(roomId: string, match: Match, actorId: string, action: GameAction): void {
    const before = match.engine.getSnapshot();
    match.engine.dispatch(actorId, action);
    this.changed({ before, after: match.engine.getSnapshot(), actorId, action });
    this.schedule(roomId, match);
  }
  private schedule(roomId: string, match: Match): void {
    const room = match.engine.getSnapshot();
    if (
      match.timer ||
      match.paused ||
      room.status !== 'PLAYING' ||
      !match.bots.has(room.currentTurnPlayerId!)
    )
      return;
    match.timer = setTimeout(() => {
      match.timer = undefined;
      if (!this.matches.has(roomId) || match.paused) return;
      try {
        const state = match.engine.getSnapshot();
        const id = state.currentTurnPlayerId!;
        this.dispatch(roomId, match, id, this.ai.decide(state, match.engine.getActionOptions(id)));
      } catch (error) {
        console.error('AI turn failed', error);
        this.failed(roomId);
      }
    }, this.delay);
  }
  private requireMatch(roomId: string): Match {
    const m = this.matches.get(roomId);
    if (!m) throw new Error('경기가 시작되지 않았습니다.');
    return m;
  }
}
