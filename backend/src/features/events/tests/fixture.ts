import christmas from '../configs/christmas.event.js';
import { EventService } from '../EventService.js';
import { LocalEventRepository } from '../EventRepository.js';
import { EventRewardService } from '../rewards/EventRewardService.js';
import { EventMissionService } from '../missions/EventMissionService.js';
import { EventShopService } from '../shop/EventShopService.js';
export function fixture(directory?: string) {
  let now = new Date('2026-12-20T01:00:00+09:00');
  const definition = structuredClone(christmas);
  definition.rewards[0]!.rewardAmount = 1000;
  const repository = new LocalEventRepository(directory);
  const events = new EventService([definition], repository, () => now);
  return {
    definition,
    repository,
    events,
    rewards: new EventRewardService(events),
    missions: new EventMissionService(events),
    shop: new EventShopService(events),
    setTime: (date: string) => {
      now = new Date(date);
    },
  };
}
