import { randomBytes, randomUUID } from 'node:crypto';
import {
  AIDifficulty,
  GameMode,
  type CreateRoomInput,
  type LobbyMember,
  type LobbyRoom,
} from '../../../shared/src/index.js';
import { SERVER_CONFIG } from '../config/server.js';
export class RoomManager {
  private readonly rooms = new Map<string, LobbyRoom>();
  private readonly locations = new Map<string, string>();
  get(roomId: string): LobbyRoom {
    return structuredClone(this.requireRoom(roomId));
  }
  find(playerId: string): LobbyRoom | null {
    const id = this.locations.get(playerId);
    return id ? this.get(id) : null;
  }
  create(playerId: string, input: Required<CreateRoomInput>): LobbyRoom {
    if (this.locations.has(playerId)) throw new Error('현재 방에서 먼저 나가세요.');
    if (this.rooms.size >= SERVER_CONFIG.maxRooms) throw new Error('서버의 방이 가득 찼습니다.');
    let roomId: string;
    do {
      roomId = randomBytes(4).toString('hex').toUpperCase();
    } while (this.rooms.has(roomId));
    const room: LobbyRoom = {
      roomId,
      hostPlayerId: playerId,
      mode: input.mode,
      capacity: input.mode === GameMode.ONE_VS_ONE ? 2 : 4,
      status: 'WAITING',
      members: [],
      paused: false,
    };
    room.members.push(this.member(playerId, input.nickname));
    if (input.mode === GameMode.SOLO_AI)
      for (let i = 1; i <= input.aiCount; i++)
        room.members.push({
          ...this.member(randomUUID(), `AI_${i}`),
          control: 'AI',
          ready: true,
          difficulty: input.difficulty,
        });
    this.rooms.set(roomId, room);
    this.locations.set(playerId, roomId);
    return this.get(roomId);
  }
  join(playerId: string, roomId: string, nickname: string): LobbyRoom {
    if (this.locations.has(playerId)) throw new Error('현재 방에서 먼저 나가세요.');
    const room = this.requireRoom(roomId);
    if (room.status !== 'WAITING' || room.mode === GameMode.SOLO_AI)
      throw new Error('입장할 수 없는 방입니다.');
    if (room.members.length >= room.capacity) throw new Error('방이 가득 찼습니다.');
    room.members.push(this.member(playerId, nickname));
    this.locations.set(playerId, roomId);
    this.resetReady(room);
    return this.get(roomId);
  }
  ready(playerId: string, ready: boolean): LobbyRoom {
    const room = this.forPlayer(playerId);
    if (room.status !== 'WAITING') throw new Error('대기방에서만 준비 상태를 바꿀 수 있습니다.');
    room.members.find((p) => p.playerId === playerId)!.ready = ready;
    return this.get(room.roomId);
  }
  validateStart(playerId: string): LobbyRoom {
    const room = this.forPlayer(playerId);
    if (room.hostPlayerId !== playerId) throw new Error('방장만 시작할 수 있습니다.');
    if (room.status !== 'WAITING') throw new Error('이미 시작한 경기입니다.');
    const count = room.members.length;
    if (count < 2 || (room.mode !== GameMode.SOLO_AI && count !== room.capacity))
      throw new Error(`이 모드는 ${room.capacity}명이 필요합니다.`);
    if (!room.members.every((p) => p.ready && p.connected))
      throw new Error('모두 연결된 상태에서 준비해야 합니다.');
    return this.get(room.roomId);
  }
  started(roomId: string): void {
    this.requireRoom(roomId).status = 'PLAYING';
  }
  finished(roomId: string): void {
    const room = this.requireRoom(roomId);
    room.status = 'FINISHED';
    room.paused = false;
  }
  connected(playerId: string, connected: boolean): LobbyRoom | null {
    const id = this.locations.get(playerId);
    if (!id) return null;
    const room = this.requireRoom(id);
    const member = room.members.find((p) => p.playerId === playerId)!;
    member.connected = connected;
    if (!connected && room.status === 'WAITING') member.ready = false;
    room.paused =
      room.status === 'PLAYING' && room.members.some((p) => p.control === 'HUMAN' && !p.connected);
    return this.get(id);
  }
  leave(playerId: string): { room: LobbyRoom | null; roomId: string; takeover: boolean } | null {
    const id = this.locations.get(playerId);
    if (!id) return null;
    const room = this.requireRoom(id);
    this.locations.delete(playerId);
    const member = room.members.find((p) => p.playerId === playerId)!;
    const takeover = room.status === 'PLAYING';
    if (takeover) {
      member.control = 'AI';
      member.connected = true;
    } else {
      room.members = room.members.filter((p) => p.playerId !== playerId);
      this.resetReady(room);
    }
    const humans = room.members.filter((p) => p.control === 'HUMAN');
    if (humans.length === 0) {
      this.rooms.delete(id);
      return { room: null, roomId: id, takeover };
    }
    if (room.hostPlayerId === playerId) room.hostPlayerId = humans[0]!.playerId;
    room.paused = room.status === 'PLAYING' && humans.some((p) => !p.connected);
    return { room: this.get(id), roomId: id, takeover };
  }
  clear(): void {
    this.rooms.clear();
    this.locations.clear();
  }
  private member(playerId: string, nickname: string): LobbyMember {
    return {
      playerId,
      nickname,
      ready: false,
      connected: true,
      control: 'HUMAN',
      difficulty: AIDifficulty.NORMAL,
      teamId: null,
    };
  }
  private resetReady(room: LobbyRoom): void {
    for (const p of room.members) if (p.control === 'HUMAN') p.ready = false;
  }
  private requireRoom(roomId: string): LobbyRoom {
    const room = this.rooms.get(roomId);
    if (!room) throw new Error('방을 찾을 수 없습니다.');
    return room;
  }
  private forPlayer(playerId: string): LobbyRoom {
    const id = this.locations.get(playerId);
    if (!id) throw new Error('방에 먼저 입장하세요.');
    return this.requireRoom(id);
  }
}
