import {
  EventType,
  type AcquisitionMethod,
  type EventDefinition,
  type RewardSpec,
} from './EventTypes.js';
import { CosmeticService } from '../cosmetics/CosmeticService.js';
export function assertWindow(from: string, until: string, now: Date): void {
  if (!(Date.parse(from) <= now.getTime() && now.getTime() < Date.parse(until)))
    throw new Error('획득 가능한 기간이 아닙니다.');
}
export class EventValidator {
  constructor(private readonly cosmetics = new CosmeticService()) {}
  validate(event: EventDefinition): void {
    const validDate = (date: string) =>
      typeof date === 'string' &&
      /(?:Z|[+-]\d{2}:\d{2})$/.test(date) &&
      Number.isFinite(Date.parse(date));
    const integer = (value: number, min = 1) => Number.isSafeInteger(value) && value >= min;
    if (
      !/^[a-z][a-z0-9_]*$/.test(event.id) ||
      !event.name ||
      !Object.values(EventType).includes(event.eventType) ||
      typeof event.active !== 'boolean' ||
      !validDate(event.startAt) ||
      !validDate(event.endAt) ||
      Date.parse(event.startAt) >= Date.parse(event.endAt)
    )
      throw new Error('이벤트 정의/기간이 올바르지 않습니다.');
    if (event.currency.eventId !== event.id) throw new Error('이벤트 재화 참조가 잘못되었습니다.');
    const ids = new Set<string>();
    for (const item of [...event.cosmetics, ...event.shop, ...event.missions, ...event.rewards]) {
      if (!/^[a-z][a-z0-9_]*$/.test(item.id) || ids.has(item.id))
        throw new Error('중복되거나 잘못된 항목 ID입니다.');
      ids.add(item.id);
      if ('eventId' in item && item.eventId !== event.id)
        throw new Error('다른 이벤트 항목입니다.');
    }
    for (const item of [...event.cosmetics, ...event.shop]) {
      if (
        !validDate(item.availableFrom) ||
        !validDate(item.availableUntil) ||
        Date.parse(item.availableFrom) < Date.parse(event.startAt) ||
        Date.parse(item.availableUntil) > Date.parse(event.endAt) ||
        Date.parse(item.availableFrom) >= Date.parse(item.availableUntil)
      )
        throw new Error('상품/스킨 기간이 이벤트 기간을 벗어납니다.');
    }
    for (const link of event.cosmetics)
      if (this.cosmetics.get(link.cosmeticId).cosmeticType !== link.cosmeticType)
        throw new Error('스킨 타입이 다릅니다.');
    const reward = (value: RewardSpec, method: AcquisitionMethod) => {
      if (
        !integer(value.rewardAmount) ||
        !['EVENT_CURRENCY', 'COIN', 'COSMETIC', 'BOX'].includes(value.rewardType)
      )
        throw new Error('보상 정의가 잘못되었습니다.');
      if (value.rewardType === 'EVENT_CURRENCY' && value.rewardId !== event.currency.id)
        throw new Error('다른 이벤트 재화를 지급할 수 없습니다.');
      if (
        value.rewardType === 'COSMETIC' &&
        (value.rewardAmount !== 1 ||
          !event.cosmetics.some(
            (c) => c.cosmeticId === value.rewardId && c.acquisitionMethod === method,
          ))
      )
        throw new Error('스킨 획득 경로가 등록되지 않았습니다.');
    };
    event.missions.forEach((m) => {
      if (
        !integer(m.targetAmount) ||
        !['PLAY_GAME', 'WIN_GAME', 'BUY_CITY', 'BUILD_LANDMARK'].includes(m.targetType)
      )
        throw new Error('미션 목표가 잘못되었습니다.');
      reward(m, 'EVENT_MISSION');
    });
    event.attendance.forEach((r) => reward(r, 'EVENT_ATTENDANCE'));
    event.rewards.forEach((r) => reward(r, 'EVENT_REWARD'));
    for (const item of event.shop) {
      if (
        !integer(item.price, 0) ||
        !integer(item.purchaseLimit) ||
        item.currencyId !== event.currency.id ||
        this.cosmetics.get(item.itemId).cosmeticType !== item.itemType ||
        !event.cosmetics.some(
          (c) => c.cosmeticId === item.itemId && c.acquisitionMethod === 'EVENT_SHOP',
        )
      )
        throw new Error('이벤트 상점 정의가 잘못되었습니다.');
    }
  }
}
