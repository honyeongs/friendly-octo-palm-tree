import type { EventAccount } from '../../../../shared/src/events.js';
import { CosmeticService } from '../cosmetics/CosmeticService.js';
export class InventoryService {
  constructor(private readonly cosmetics = new CosmeticService()) {}
  grant(account: EventAccount, cosmeticId: string, now: Date, source: string): void {
    this.cosmetics.get(cosmeticId);
    if (account.inventory[cosmeticId]) return;
    account.inventory[cosmeticId] = { cosmeticId, acquiredAt: now.toISOString(), source };
  }
  equip(account: EventAccount, cosmeticId: string): void {
    const item = this.cosmetics.get(cosmeticId);
    // Ownership survives event expiry. No event dates or acquisition windows are consulted.
    if (item.acquisitionType !== 'DEFAULT' && !account.inventory[cosmeticId])
      throw new Error('보유하지 않은 스킨입니다.');
    account.equipped[item.cosmeticType] = item.id;
  }
}
