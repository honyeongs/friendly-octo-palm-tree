import type { Server, Socket } from 'socket.io';
import {
  GameMode,
  type Ack,
  type ClientToServerEvents,
  type GameAction,
  type ServerToClientEvents,
} from '../../../shared/src/index.js';
import type { EngineOptions } from '../engine/GameEngine.js';
import { SERVER_CONFIG } from '../config/server.js';
import { RoomManager } from './RoomManager.js';
import { MatchManager, type MatchChange } from './MatchManager.js';
import { SessionStore, type PlayerSession } from './SessionStore.js';
import { parseAction, parseCreate, parseJoin, parseReady } from './validation.js';

type SocketData = { session: PlayerSession };
export type GameServer = Server<
  ClientToServerEvents,
  ServerToClientEvents,
  Record<string, never>,
  SocketData
>;
export type GameSocket = Socket<
  ClientToServerEvents,
  ServerToClientEvents,
  Record<string, never>,
  SocketData
>;
export interface HandlerOptions {
  aiDelayMs?: number;
  reconnectGraceMs?: number;
  maxRequestsPerSecond?: number;
  engineOptions?: () => EngineOptions;
  identityFile?: string;
  onMatchChange?: (change: MatchChange, eligibleIds: string[]) => void;
}
export class SocketHandler {
  private readonly rooms = new RoomManager();
  private readonly sessions: SessionStore;
  private readonly matches: MatchManager;
  private readonly sockets = new Map<string, GameSocket>();
  private readonly expirations = new Map<string, ReturnType<typeof setTimeout>>();
  private closed = false;
  constructor(
    io: GameServer,
    private readonly options: HandlerOptions = {},
  ) {
    this.sessions = new SessionStore(options.identityFile);
    this.matches = new MatchManager(
      (change) => this.changed(change),
      (id) => this.broadcastError(id, 'AI 처리 중 오류가 발생했습니다.'),
      options.aiDelayMs,
      options.engineOptions,
    );
    io.use((socket, next) => {
      try {
        socket.data.session = this.sessions.connect(socket.handshake.auth.sessionToken, socket.id);
        next();
      } catch (error) {
        next(new Error(error instanceof Error ? error.message : 'INVALID_SESSION'));
      }
    });
    io.on('connection', (socket) => this.attach(socket));
  }
  close(): void {
    this.closed = true;
    for (const timer of this.expirations.values()) clearTimeout(timer);
    this.expirations.clear();
    this.matches.close();
    this.rooms.clear();
    this.sessions.clear();
    this.sockets.clear();
  }
  private attach(socket: GameSocket): void {
    const session = socket.data.session;
    const id = session.playerId;
    const pending = this.expirations.get(id);
    if (pending) clearTimeout(pending);
    this.expirations.delete(id);
    this.sockets.set(id, socket);
    socket.emit('session', { playerId: id, sessionToken: session.token });
    const restored = this.rooms.connected(id, true);
    if (restored) {
      this.matches.sync(restored);
      this.publish(restored.roomId);
    } else socket.emit('room_updated', { room: null, you: id });
    let windowStart = Date.now();
    let requests = 0;
    const run = (ack: Ack, action: () => void) => {
      if (typeof ack !== 'function') {
        socket.emit('error', '응답 콜백이 필요합니다.');
        return;
      }
      try {
        if (session.socketId !== socket.id) throw new Error('유효하지 않은 연결입니다.');
        if (Date.now() - windowStart >= 1000) {
          requests = 0;
          windowStart = Date.now();
        }
        if (++requests > (this.options.maxRequestsPerSecond ?? SERVER_CONFIG.maxActionsPerSecond))
          throw new Error('요청이 너무 빠릅니다. 잠시 후 다시 시도하세요.');
        action();
        ack({ ok: true, data: null });
      } catch (error) {
        const message = error instanceof Error ? error.message : '요청 처리에 실패했습니다.';
        socket.emit('error', message);
        ack({ ok: false, error: message });
        const room = this.rooms.find(id);
        if (room?.status !== 'WAITING' && room)
          socket.emit('game_state_updated', this.matches.view(room.roomId, id));
      }
    };
    socket.on('create_room', (input, ack) =>
      run(ack, () => {
        const room = this.rooms.create(id, parseCreate(input));
        if (room.mode === GameMode.SOLO_AI) {
          this.rooms.ready(id, true);
          this.start(id);
        } else this.publish(room.roomId);
      }),
    );
    socket.on('join_room', (input, ack) =>
      run(ack, () => {
        const parsed = parseJoin(input);
        this.publish(this.rooms.join(id, parsed.roomId, parsed.nickname).roomId);
      }),
    );
    socket.on('ready', (input, ack) =>
      run(ack, () => this.publish(this.rooms.ready(id, parseReady(input)).roomId)),
    );
    socket.on('start_game', (_input, ack) => run(ack, () => this.start(id)));
    socket.on('leave_room', (_input, ack) => run(ack, () => this.leave(id)));
    const action = (type: GameAction['type'], input: unknown, ack: Ack) =>
      run(ack, () => {
        const request = parseAction(input);
        const room = this.rooms.find(id);
        if (!room || room.roomId !== request.roomId)
          throw new Error('참가한 방의 행동만 요청할 수 있습니다.');
        this.matches.act(room.roomId, id, { type }, request.expectedRevision);
      });
    socket.on('roll_dice', (input, ack) => action('ROLL', input, ack));
    socket.on('buy_property', (input, ack) => action('BUY', input, ack));
    socket.on('upgrade_property', (input, ack) => action('UPGRADE', input, ack));
    socket.on('end_turn', (input, ack) => action('END_TURN', input, ack));
    socket.on('disconnect', () => {
      if (this.closed || !this.sessions.disconnect(session, socket.id)) return;
      this.sockets.delete(id);
      const room = this.rooms.connected(id, false);
      if (room) {
        this.matches.sync(room);
        this.publish(room.roomId);
      }
      this.expirations.set(
        id,
        setTimeout(() => {
          this.expirations.delete(id);
          this.leave(id);
          this.sessions.expire(session);
        }, this.options.reconnectGraceMs ?? SERVER_CONFIG.reconnectGraceMs),
      );
    });
  }
  private start(playerId: string): void {
    const room = this.rooms.validateStart(playerId);
    this.matches.create(room);
    this.rooms.started(room.roomId);
    this.publish(room.roomId, true);
    this.matches.sync(this.rooms.get(room.roomId));
  }
  private leave(playerId: string): void {
    const result = this.rooms.leave(playerId);
    this.sockets.get(playerId)?.emit('room_updated', { room: null, you: playerId });
    if (!result) return;
    if (!result.room) this.matches.remove(result.roomId);
    else {
      this.matches.sync(result.room);
      this.publish(result.roomId);
    }
  }
  private recipients(roomId: string): GameSocket[] {
    return this.rooms
      .get(roomId)
      .members.filter((p) => p.control === 'HUMAN')
      .flatMap((p) => {
        const s = this.sockets.get(p.playerId);
        return s ? [s] : [];
      });
  }
  private publish(roomId: string, started = false): void {
    const room = this.rooms.get(roomId);
    for (const socket of this.recipients(roomId)) {
      const id = socket.data.session.playerId;
      socket.emit('room_updated', { room, you: id });
      if (room.status !== 'WAITING') {
        const view = this.matches.view(roomId, id);
        if (started) socket.emit('game_started', view);
        socket.emit('game_state_updated', view);
      }
    }
  }
  private changed({ before, after, actorId, action }: MatchChange): void {
    const roomId = after.roomId;
    if (after.status === 'FINISHED') this.rooms.finished(roomId);
    const base = { roomId, revision: after.gameState.revision, playerId: actorId };
    for (const socket of this.recipients(roomId)) {
      const roll = after.gameState.lastRoll;
      if (action.type === 'ROLL' && roll) {
        socket.emit('dice_rolled', { ...base, dice: roll.dice });
        socket.emit('player_moved', { ...base, from: roll.from, to: roll.to });
        socket.emit('tile_resolved', { ...base, tile: after.gameState.tiles[roll.to]! });
      }
      for (const id of after.gameState.bankruptcyOrder.filter(
        (id) => !before.gameState.bankruptcyOrder.includes(id),
      ))
        socket.emit('player_bankrupt', { ...base, playerId: id });
    }
    this.publish(roomId);
    if (after.status === 'FINISHED')
      for (const socket of this.recipients(roomId)) socket.emit('game_finished', after);
    this.options.onMatchChange?.(
      { before, after, actorId, action },
      this.rooms
        .get(roomId)
        .members.filter((p) => p.control === 'HUMAN')
        .map((p) => p.playerId),
    );
  }
  private broadcastError(roomId: string, message: string): void {
    for (const socket of this.recipients(roomId)) socket.emit('error', message);
  }
}
