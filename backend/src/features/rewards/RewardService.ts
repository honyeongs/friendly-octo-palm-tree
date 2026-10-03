import { randomUUID } from 'node:crypto';
import type { EventAccount, RewardSpec } from '../../../../shared/src/events.js';
import { InventoryService } from '../inventory/InventoryService.js';
export class RewardService {
  constructor(private readonly inventory = new InventoryService()) {}
  grant(
    account: EventAccount,
    reward: RewardSpec,
    eventId: string,
    source: string,
    now: Date,
  ): void {
    if (!Number.isSafeInteger(reward.rewardAmount) || reward.rewardAmount <= 0)
      throw new Error('잘못된 보상 수량입니다.');
    const add = (current: number) => {
      const result = current + reward.rewardAmount;
      if (!Number.isSafeInteger(result)) throw new Error('재화 한도를 초과했습니다.');
      return result;
    };
    switch (reward.rewardType) {
      case 'EVENT_CURRENCY':
        account.currencies[reward.rewardId] = add(account.currencies[reward.rewardId] ?? 0);
        break;
      case 'COIN':
        account.coins = add(account.coins);
        break;
      case 'BOX':
        account.boxes[reward.rewardId] = add(account.boxes[reward.rewardId] ?? 0);
        break;
      case 'COSMETIC':
        this.inventory.grant(account, reward.rewardId, now, source);
        break;
    }
    account.history.push({
      id: randomUUID(),
      eventId,
      userId: account.userId,
      source,
      reward,
      grantedAt: now.toISOString(),
    });
    const participation = account.participation[eventId];
    if (participation) participation.rewardsClaimed++;
  }
}
