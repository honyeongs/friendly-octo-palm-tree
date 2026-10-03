import { useEffect, useRef, useState } from 'react';
import { io, type Socket } from 'socket.io-client';
import type { EventDashboard } from '../../shared/src/events';
import type {
  Ack,
  ClientToServerEvents,
  CreateRoomInput,
  GameAction,
  LobbyView,
  RoomView,
  ServerToClientEvents,
} from '../../shared/src/index';
type GameSocket = Socket<ServerToClientEvents, ClientToServerEvents>;
const SESSION_KEY = 'starlane-session';
function token(): string | undefined {
  try {
    return sessionStorage.getItem(SESSION_KEY) ?? undefined;
  } catch {
    return undefined;
  }
}
export function useGame() {
  const socket = useRef<GameSocket | null>(null);
  const [view, setView] = useState<RoomView | null>(null);
  const [lobby, setLobby] = useState<LobbyView | null>(null);
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [events, setEvents] = useState<EventDashboard | null>(null);
  const pending = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    const connection: GameSocket = io({
      auth: { sessionToken: token() },
      reconnectionAttempts: 20,
    });
    socket.current = connection;
    connection.on('session', (session) => {
      try {
        sessionStorage.setItem(SESSION_KEY, session.sessionToken);
      } catch {
        /* Memory auth still supports connection retries. */
      }
      connection.auth = { sessionToken: session.sessionToken };
      connection.emit('events_get', {}, () => {});
    });
    connection.on('connect', () => {
      setConnected(true);
      setError('');
    });
    connection.on('disconnect', () => {
      setConnected(false);
      setBusy(false);
      if (pending.current) clearTimeout(pending.current);
      pending.current = null;
      setError('연결이 끊겼습니다. 60초 안에 재접속하면 같은 플레이어로 복귀합니다.');
    });
    connection.on('connect_error', (error) => {
      if (error.message === 'SESSION_EXPIRED' || error.message === 'INVALID_SESSION') {
        try {
          sessionStorage.removeItem(SESSION_KEY);
        } catch {
          /* No storage available. */
        }
        connection.auth = {};
        setView(null);
        setLobby(null);
        connection.connect();
      } else
        setError(
          error.message === 'SESSION_IN_USE'
            ? '이 세션은 다른 탭에서 사용 중입니다. 별도의 브라우저 또는 새 탭에서 접속하세요.'
            : '서버에 연결할 수 없습니다. 서버 실행 상태를 확인하세요.',
        );
    });
    connection.on('room_updated', (next) => {
      setLobby(next);
      if (!next.room || next.room.status === 'WAITING') setView(null);
    });
    connection.on('game_started', setView);
    connection.on('game_state_updated', setView);
    connection.on('error', setError);
    connection.on('events_updated', setEvents);
    return () => {
      if (pending.current) clearTimeout(pending.current);
      pending.current = null;
      connection.removeAllListeners();
      connection.disconnect();
      socket.current = null;
    };
  }, []);
  const request = (emit: (s: GameSocket, ack: Ack) => void) => {
    if (!socket.current?.connected || pending.current) return;
    setBusy(true);
    setError('');
    const timer = setTimeout(() => {
      pending.current = null;
      setBusy(false);
      setError('응답 시간이 초과되었습니다. 현재 방 상태를 확인하세요.');
    }, 5000);
    pending.current = timer;
    emit(socket.current, (reply) => {
      if (pending.current !== timer) return;
      clearTimeout(timer);
      pending.current = null;
      setBusy(false);
      if (!reply.ok) setError(reply.error);
    });
  };
  const create = (input: CreateRoomInput) => request((s, ack) => s.emit('create_room', input, ack));
  const join = (roomId: string, nickname: string) =>
    request((s, ack) => s.emit('join_room', { roomId, nickname }, ack));
  const ready = (value: boolean) => request((s, ack) => s.emit('ready', { ready: value }, ack));
  const start = () => request((s, ack) => s.emit('start_game', {}, ack));
  const leave = () => request((s, ack) => s.emit('leave_room', {}, ack));
  const act = (action: GameAction) => {
    if (!view) return;
    const events = {
      ROLL: 'roll_dice',
      BUY: 'buy_property',
      UPGRADE: 'upgrade_property',
      END_TURN: 'end_turn',
    } as const;
    request((s, ack) =>
      s.emit(
        events[action.type],
        { roomId: view.room.roomId, expectedRevision: view.room.gameState.revision },
        ack,
      ),
    );
  };
  const refreshEvents = () => request((s, ack) => s.emit('events_get', {}, ack));
  const eventAction = (
    event:
      | 'event_shop_buy'
      | 'event_mission_claim'
      | 'event_reward_claim'
      | 'event_attendance_claim'
      | 'cosmetic_equip',
    eventId: string,
    itemId?: string,
  ) => request((s, ack) => s.emit(event, { eventId, itemId }, ack));
  return {
    view,
    lobby,
    connected,
    busy,
    error,
    create,
    join,
    ready,
    start,
    leave,
    act,
    events,
    refreshEvents,
    eventAction,
  };
}
