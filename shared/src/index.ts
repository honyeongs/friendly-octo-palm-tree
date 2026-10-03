export enum GameMode {
  SOLO_AI = 'SOLO_AI',
  ONE_VS_ONE = 'ONE_VS_ONE',
  TWO_VS_TWO = 'TWO_VS_TWO',
  FOUR_PLAYER_FFA = 'FOUR_PLAYER_FFA',
}
export enum AIDifficulty {
  EASY = 'EASY',
  NORMAL = 'NORMAL',
  HARD = 'HARD',
}
export type TileType = 'START' | 'CITY' | 'EVENT' | 'REST' | 'TRAVEL';
export type SpecialEffect =
  { kind: 'EVENT' } | { kind: 'REST'; turns: number } | { kind: 'TRAVEL'; destination: number };
export interface Player {
  id: string;
  nickname: string;
  money: number;
  position: number;
  ownedTileIds: string[];
  isAI: boolean;
  teamId: string | null;
  isBankrupt: boolean;
  rp: number;
  skipTurns: number;
  difficulty: AIDifficulty;
}
export interface Tile {
  id: string;
  index: number;
  type: TileType;
  name: string;
  purchasePrice: number;
  baseToll: number;
  ownerId: string | null;
  buildingLevel: number;
  specialEffect: SpecialEffect | null;
  groupId: string | null;
}
export type GameAction =
  { type: 'ROLL' } | { type: 'BUY' } | { type: 'UPGRADE' } | { type: 'END_TURN' };
export interface GameLog {
  sequence: number;
  turn: number;
  message: string;
}
export interface GameState {
  tiles: Tile[];
  phase: 'WAITING' | 'AWAIT_ROLL' | 'AWAIT_ACTION' | 'FINISHED';
  dice: [number, number] | null;
  lastRoll: {
    playerId: string;
    dice: [number, number];
    from: number;
    to: number;
    tileId: string;
  } | null;
  winnerIds: string[];
  bankruptcyOrder: string[];
  logs: GameLog[];
  hasBuiltThisTurn: boolean;
  revision: number;
}
export interface GameRoom {
  roomId: string;
  players: Player[];
  gameState: GameState;
  currentTurnPlayerId: string | null;
  turnNumber: number;
  mode: GameMode;
  status: 'WAITING' | 'PLAYING' | 'FINISHED';
}
export interface PlayerInput {
  id: string;
  nickname: string;
  isAI?: boolean;
  teamId?: string | null;
  difficulty?: AIDifficulty;
}
export interface ActionOptions {
  canRoll: boolean;
  canBuy: boolean;
  canUpgrade: boolean;
  canEndTurn: boolean;
  upgradePrice: number;
  toll: number;
}
export interface RoomView {
  room: GameRoom;
  you: string;
  options: ActionOptions;
}
export type Reply<T> = { ok: true; data: T } | { ok: false; error: string };
export interface ClientToServerEvents {
  events_get: (input: Record<string, never>, ack: Ack) => void;
  event_shop_buy: (input: EventRequest, ack: Ack) => void;
  event_mission_claim: (input: EventRequest, ack: Ack) => void;
  event_reward_claim: (input: EventRequest, ack: Ack) => void;
  event_attendance_claim: (input: EventRequest, ack: Ack) => void;
  cosmetic_equip: (input: EventRequest, ack: Ack) => void;
  create_room: (input: CreateRoomInput, ack: Ack) => void;
  join_room: (input: { roomId: string; nickname: string }, ack: Ack) => void;
  leave_room: (input: Record<string, never>, ack: Ack) => void;
  ready: (input: { ready: boolean }, ack: Ack) => void;
  start_game: (input: Record<string, never>, ack: Ack) => void;
  roll_dice: (input: ActionRequest, ack: Ack) => void;
  buy_property: (input: ActionRequest, ack: Ack) => void;
  upgrade_property: (input: ActionRequest, ack: Ack) => void;
  end_turn: (input: ActionRequest, ack: Ack) => void;
}
export interface ServerToClientEvents {
  events_updated: (dashboard: import('./events.js').EventDashboard) => void;
  session: (session: { playerId: string; sessionToken: string }) => void;
  room_updated: (view: LobbyView) => void;
  game_started: (view: RoomView) => void;
  game_state_updated: (view: RoomView) => void;
  dice_rolled: (event: MatchEvent & { dice: [number, number] }) => void;
  player_moved: (event: MatchEvent & { from: number; to: number }) => void;
  tile_resolved: (event: MatchEvent & { tile: Tile }) => void;
  player_bankrupt: (event: MatchEvent) => void;
  game_finished: (room: GameRoom) => void;
  error: (message: string) => void;
}
export type Ack = (reply: Reply<null>) => void;
export interface EventRequest {
  eventId: string;
  itemId?: string;
}
export interface ActionRequest {
  roomId: string;
  expectedRevision: number;
}
export interface CreateRoomInput {
  nickname: string;
  mode: GameMode;
  aiCount?: number;
  difficulty?: AIDifficulty;
}
export interface LobbyMember {
  playerId: string;
  nickname: string;
  ready: boolean;
  connected: boolean;
  control: 'HUMAN' | 'AI';
  difficulty: AIDifficulty;
  teamId: string | null;
}
export interface LobbyRoom {
  roomId: string;
  hostPlayerId: string;
  mode: GameMode;
  capacity: number;
  status: 'WAITING' | 'PLAYING' | 'FINISHED';
  members: LobbyMember[];
  paused: boolean;
}
export interface LobbyView {
  room: LobbyRoom | null;
  you: string;
}
export interface MatchEvent {
  roomId: string;
  revision: number;
  playerId: string;
}
