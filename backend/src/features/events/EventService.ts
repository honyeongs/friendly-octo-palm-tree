import type {
  AcquisitionMethod,
  EventAccount,
  EventDashboard,
  EventDefinition,
  EventStatus,
  RewardSpec,
  ServerClock,
} from './EventTypes.js';
import type { EventRepository } from './EventRepository.js';
import { assertWindow, EventValidator } from './EventValidator.js';
import { CosmeticService } from '../cosmetics/CosmeticService.js';
export class EventService {
  private definitions: EventDefinition[];
  constructor(
    definitions: EventDefinition[],
    readonly repository: EventRepository,
    readonly clock: ServerClock = () => new Date(),
  ) {
    this.definitions = [];
    this.replaceDefinitions(definitions);
  }
  // Future admin adapters can validate and publish an entire config revision here.
  replaceDefinitions(definitions: EventDefinition[]): void {
    const ids = new Set<string>();
    const nested = new Set<string>();
    for (const event of definitions) {
      new EventValidator().validate(event);
      if (ids.has(event.id)) throw new Error('중복 이벤트 ID입니다.');
      ids.add(event.id);
      for (const id of [
        event.currency.id,
        ...event.missions.map((m) => m.id),
        ...event.shop.map((s) => s.id),
        ...event.rewards.map((r) => r.id),
      ]) {
        if (nested.has(id)) throw new Error('이벤트 간 항목 ID가 중복됩니다.');
        nested.add(id);
      }
    }
    this.definitions = structuredClone(definitions);
  }
  list(): EventDefinition[] {
    return structuredClone(this.definitions);
  }
  getEventStatus(event: EventDefinition, now = this.clock()): EventStatus {
    if (now.getTime() < Date.parse(event.startAt)) return 'UPCOMING';
    return now.getTime() < Date.parse(event.endAt) ? 'ACTIVE' : 'ENDED';
  }
  available(eventId: string, now = this.clock()): EventDefinition {
    const event = this.definitions.find((e) => e.id === eventId);
    if (!event || !event.active || this.getEventStatus(event, now) !== 'ACTIVE')
      throw new Error('진행 중인 이벤트가 아닙니다.');
    return structuredClone(event);
  }
  validateReward(
    event: EventDefinition,
    reward: RewardSpec,
    method: AcquisitionMethod,
    now: Date,
  ): void {
    if (reward.rewardType !== 'COSMETIC') return;
    const link = event.cosmetics.find(
      (c) =>
        c.cosmeticId === reward.rewardId &&
        c.acquisitionMethod === method &&
        Date.parse(c.availableFrom) <= now.getTime() &&
        now.getTime() < Date.parse(c.availableUntil),
    );
    if (!link) throw new Error('이 스킨을 현재 획득할 수 없습니다.');
    assertWindow(link.availableFrom, link.availableUntil, now);
  }
  participate(account: EventAccount, eventId: string, now: Date): void {
    account.participation[eventId] ??= {
      userId: account.userId,
      eventId,
      joinedAt: now.toISOString(),
      missionsCompleted: 0,
      rewardsClaimed: 0,
    };
  }
  async dashboard(userId: string): Promise<EventDashboard> {
    const account = await this.repository.read(userId);
    const now = this.clock();
    return {
      serverTime: now.toISOString(),
      account,
      cosmetics: new CosmeticService().list(),
      events: this.list().map((definition) => ({
        definition,
        status: this.getEventStatus(definition, now),
        remainingMs: Math.max(0, Date.parse(definition.endAt) - now.getTime()),
      })),
    };
  }
}
