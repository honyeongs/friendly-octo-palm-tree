import { loadEventConfigs } from './configs/load.js';
import { EventService } from './EventService.js';
import { LocalEventRepository, type EventRepository } from './EventRepository.js';
import { EventRewardService } from './rewards/EventRewardService.js';
import { EventMissionService } from './missions/EventMissionService.js';
import { EventShopService } from './shop/EventShopService.js';
import type { ServerClock } from './EventTypes.js';
export async function createEventSystem(
  repository: EventRepository = new LocalEventRepository(),
  clock?: ServerClock,
) {
  const events = new EventService(await loadEventConfigs(), repository, clock);
  return {
    events,
    rewards: new EventRewardService(events),
    missions: new EventMissionService(events),
    shop: new EventShopService(events),
  };
}
export type EventSystem = Awaited<ReturnType<typeof createEventSystem>>;
