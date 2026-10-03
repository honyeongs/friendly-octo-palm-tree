import type { EventService } from '../EventService.js';
import { RewardService } from '../../rewards/RewardService.js';
import { AttendanceService } from '../../attendance/AttendanceService.js';
export class EventRewardService {
  constructor(
    private readonly events: EventService,
    private readonly rewards = new RewardService(),
  ) {}
  claim(userId: string, eventId: string, rewardId: string): Promise<void> {
    return this.events.repository.transaction(userId, (account) => {
      const now = this.events.clock();
      const event = this.events.available(eventId, now);
      const reward = event.rewards.find((r) => r.id === rewardId);
      if (!reward) throw new Error('보상을 찾을 수 없습니다.');
      const key = `reward:${eventId}:${rewardId}`;
      if (account.claims.includes(key)) throw new Error('이미 수령한 보상입니다.');
      this.events.validateReward(event, reward, 'EVENT_REWARD', now);
      this.events.participate(account, eventId, now);
      this.rewards.grant(account, reward, eventId, key, now);
      account.claims.push(key);
    });
  }
  attendance(userId: string, eventId: string): Promise<void> {
    return this.events.repository.transaction(userId, (account) => {
      const now = this.events.clock();
      const event = this.events.available(eventId, now);
      const index = new AttendanceService().claimDay(
        account,
        `event:${eventId}`,
        now,
        event.attendance.length,
      );
      const reward = event.attendance[index]!;
      this.events.validateReward(event, reward, 'EVENT_ATTENDANCE', now);
      this.events.participate(account, eventId, now);
      this.rewards.grant(account, reward, eventId, `attendance:${eventId}:${index + 1}`, now);
    });
  }
}
