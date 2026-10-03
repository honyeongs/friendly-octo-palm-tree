import { io, type Socket } from 'socket.io-client';
import type {
  ClientToServerEvents,
  LobbyView,
  Reply,
  RoomView,
  ServerToClientEvents,
  GameRoom,
} from '../../shared/src/index.js';
export class TestClient {
  readonly socket: Socket<ServerToClientEvents, ClientToServerEvents>;
  session?: { playerId: string; sessionToken: string };
  lobby?: LobbyView;
  view?: RoomView;
  finished?: GameRoom;
  readonly events: string[] = [];
  private readonly updates = new Set<() => void>();
  constructor(url: string, token?: string) {
    this.socket = io(url, {
      transports: ['websocket'],
      forceNew: true,
      autoConnect: false,
      reconnection: false,
      auth: { sessionToken: token },
    });
    this.socket.on('session', (session) => {
      this.session = session;
      this.notify();
    });
    this.socket.on('room_updated', (lobby) => {
      this.lobby = lobby;
      if (!lobby.room) this.view = undefined;
      this.notify();
    });
    this.socket.on('game_state_updated', (view) => {
      this.view = view;
      this.notify();
    });
    this.socket.on('game_finished', (room) => {
      this.finished = room;
      this.notify();
    });
    this.socket.on('game_started', () => this.events.push('game_started'));
    this.socket.on('dice_rolled', () => this.events.push('dice_rolled'));
    this.socket.on('player_moved', () => this.events.push('player_moved'));
    this.socket.on('tile_resolved', () => this.events.push('tile_resolved'));
    this.socket.on('player_bankrupt', () => this.events.push('player_bankrupt'));
  }
  async connect(): Promise<void> {
    const connected = new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('Connect timeout')), 3000);
      this.socket.once('session', () => {
        clearTimeout(timer);
        resolve();
      });
      this.socket.once('connect_error', (error) => {
        clearTimeout(timer);
        reject(error);
      });
    });
    this.socket.connect();
    await connected;
    await this.until(() => !!this.lobby);
  }
  async send(event: keyof ClientToServerEvents, input: unknown = {}): Promise<Reply<null>> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`Ack timeout: ${event}`)), 3000);
      // Deliberately send unknown payloads through the real network validation boundary.
      this.socket.emit(event, input as never, (reply) => {
        clearTimeout(timer);
        resolve(reply);
      });
    });
  }
  async ok(event: keyof ClientToServerEvents, input: unknown = {}): Promise<void> {
    const reply = await this.send(event, input);
    if (!reply.ok) throw new Error(reply.error);
  }
  actionRequest() {
    return { roomId: this.view!.room.roomId, expectedRevision: this.view!.room.gameState.revision };
  }
  until(predicate: () => boolean, timeout = 3000): Promise<void> {
    if (predicate()) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.updates.delete(check);
        reject(new Error('State wait timeout'));
      }, timeout);
      const check = () => {
        if (predicate()) {
          clearTimeout(timer);
          this.updates.delete(check);
          resolve();
        }
      };
      this.updates.add(check);
    });
  }
  private notify() {
    for (const update of this.updates) update();
  }
}
