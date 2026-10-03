import type { EventService } from '../EventService.js';
import type { GameFact } from '../EventTypes.js';
import { RewardService } from '../../rewards/RewardService.js';
export class EventMissionService {
  constructor(
    private readonly events: EventService,
    private readonly rewards = new RewardService(),
  ) {}
  record(fact: GameFact): Promise<void> {
    return this.events.repository.transaction(fact.userId, (account) => {
      if (account.processedFacts.includes(fact.id)) return;
      const now = this.events.clock();
      const occurred = Date.parse(fact.occurredAt);
      if (!Number.isFinite(occurred) || occurred > now.getTime())
        throw new Error('유효하지 않은 서버 게임 기록입니다.');
      for (const event of this.events.list()) {
        if (
          !event.active ||
          this.events.getEventStatus(event, now) !== 'ACTIVE' ||
          occurred < Date.parse(event.startAt) ||
          occurred >= Date.parse(event.endAt)
        )
          continue;
        for (const mission of event.missions.filter((m) => m.targetType === fact.target)) {
          this.events.participate(account, event.id, now);
          const progress = account.missions[mission.id] ?? { progress: 0, claimed: false };
          if (progress.progress < mission.targetAmount) {
            progress.progress++;
            if (progress.progress === mission.targetAmount)
              account.participation[event.id]!.missionsCompleted++;
          }
          account.missions[mission.id] = progress;
        }
      }
      account.processedFacts.push(fact.id);
    });
  }
  claim(userId: string, eventId: string, missionId: string): Promise<void> {
    return this.events.repository.transaction(userId, (account) => {
      const now = this.events.clock();
      const event = this.events.available(eventId, now);
      const mission = event.missions.find((m) => m.id === missionId);
      if (!mission) throw new Error('미션을 찾을 수 없습니다.');
      const progress = account.missions[missionId];
      if (!progress || progress.progress < mission.targetAmount)
        throw new Error('미션을 완료하지 않았습니다.');
      if (progress.claimed) throw new Error('이미 수령한 미션 보상입니다.');
      this.events.validateReward(event, mission, 'EVENT_MISSION', now);
      this.events.participate(account, eventId, now);
      this.rewards.grant(account, mission, eventId, `mission:${missionId}`, now);
      progress.claimed = true;
    });
  }
}
