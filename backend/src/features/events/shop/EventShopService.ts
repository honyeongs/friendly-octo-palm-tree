import type { EventService } from '../EventService.js';
import { assertWindow } from '../EventValidator.js';
import { RewardService } from '../../rewards/RewardService.js';
export class EventShopService {
  constructor(
    private readonly events: EventService,
    private readonly rewards = new RewardService(),
  ) {}
  buy(userId: string, eventId: string, itemId: string): Promise<void> {
    return this.events.repository.transaction(userId, (account) => {
      const now = this.events.clock();
      const event = this.events.available(eventId, now);
      const item = event.shop.find((s) => s.id === itemId);
      if (!item) throw new Error('상품을 찾을 수 없습니다.');
      assertWindow(item.availableFrom, item.availableUntil, now);
      const count = account.purchases[item.id] ?? 0;
      if (count >= item.purchaseLimit) throw new Error('구매 제한에 도달했습니다.');
      if (account.inventory[item.itemId]) throw new Error('이미 보유한 스킨입니다.');
      const balance = account.currencies[item.currencyId] ?? 0;
      if (balance < item.price) throw new Error('이벤트 재화가 부족합니다.');
      const reward = { rewardType: 'COSMETIC' as const, rewardId: item.itemId, rewardAmount: 1 };
      this.events.validateReward(event, reward, 'EVENT_SHOP', now);
      this.events.participate(account, eventId, now);
      // Charge, grant, receipt, and history commit together or all roll back.
      account.currencies[item.currencyId] = balance - item.price;
      account.purchases[item.id] = count + 1;
      this.rewards.grant(account, reward, eventId, `shop:${item.id}:${count + 1}`, now);
    });
  }
}
