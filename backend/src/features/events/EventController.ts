import type { GameSocket } from '../../server/SocketHandler.js';
import type { Ack } from '../../../../shared/src/index.js';
import type { EventSystem } from './index.js';
import { InventoryService } from '../inventory/InventoryService.js';
function ids(input: unknown): { eventId: string; itemId: string } {
  if (!input || typeof input !== 'object') throw new Error('올바른 요청이 필요합니다.');
  const data = input as Record<string, unknown>;
  if (
    typeof data.eventId !== 'string' ||
    data.eventId.length > 100 ||
    (data.itemId !== undefined && (typeof data.itemId !== 'string' || data.itemId.length > 100))
  )
    throw new Error('이벤트/항목 ID가 올바르지 않습니다.');
  return { eventId: data.eventId, itemId: typeof data.itemId === 'string' ? data.itemId : '' };
}
export class EventController {
  constructor(private readonly system: Promise<EventSystem>) {}
  attach(socket: GameSocket): void {
    const userId = socket.data.session.playerId;
    let windowStart = 0;
    let requests = 0;
    const run = async (ack: Ack, action: (system: EventSystem) => Promise<unknown>) => {
      if (typeof ack !== 'function') return;
      try {
        if (Date.now() - windowStart >= 1000) {
          windowStart = Date.now();
          requests = 0;
        }
        if (++requests > 12) throw new Error('이벤트 요청이 너무 빠릅니다.');
        const system = await this.system;
        if (!socket.connected || socket.data.session.socketId !== socket.id)
          throw new Error('유효하지 않은 세션입니다.');
        await action(system);
        socket.emit('events_updated', await system.events.dashboard(userId));
        ack({ ok: true, data: null });
      } catch (error) {
        ack({ ok: false, error: error instanceof Error ? error.message : '이벤트 요청 실패' });
      }
    };
    socket.on('events_get', (_input, ack) => {
      void run(ack, async () => {});
    });
    socket.on('event_shop_buy', (input, ack) => {
      void run(ack, (s) => {
        const { eventId, itemId } = ids(input);
        return s.shop.buy(userId, eventId, itemId);
      });
    });
    socket.on('event_mission_claim', (input, ack) => {
      void run(ack, (s) => {
        const { eventId, itemId } = ids(input);
        return s.missions.claim(userId, eventId, itemId);
      });
    });
    socket.on('event_reward_claim', (input, ack) => {
      void run(ack, (s) => {
        const { eventId, itemId } = ids(input);
        return s.rewards.claim(userId, eventId, itemId);
      });
    });
    socket.on('event_attendance_claim', (input, ack) => {
      void run(ack, (s) => s.rewards.attendance(userId, ids(input).eventId));
    });
    socket.on('cosmetic_equip', (input, ack) => {
      void run(ack, (s) =>
        s.events.repository.transaction(userId, (account) =>
          new InventoryService().equip(account, ids(input).itemId),
        ),
      );
    });
  }
}
