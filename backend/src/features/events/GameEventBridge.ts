import type { MatchChange } from '../../server/MatchManager.js';
import type { EventSystem } from './index.js';
import type { GameFact, MissionTarget } from './EventTypes.js';
// Adapter consumes committed server game transitions. It never mutates or imports GameEngine.
export async function recordMatchChange(
  system: EventSystem,
  change: MatchChange,
  eligibleIds: string[],
): Promise<void> {
  const { before, after, actorId, action } = change;
  const facts: GameFact[] = [];
  const occurredAt = system.events.clock().toISOString();
  const add = (userId: string, target: MissionTarget) => {
    if (eligibleIds.includes(userId))
      facts.push({
        id: `${after.roomId}:${after.gameState.revision}:${userId}:${target}`,
        userId,
        target,
        occurredAt,
      });
  };
  if (action.type === 'BUY') add(actorId, 'BUY_CITY');
  if (
    action.type === 'UPGRADE' &&
    after.gameState.tiles.some(
      (t) =>
        t.ownerId === actorId &&
        t.buildingLevel === 3 &&
        before.gameState.tiles[t.index]!.buildingLevel < 3,
    )
  )
    add(actorId, 'BUILD_LANDMARK');
  if (after.status === 'FINISHED' && before.status !== 'FINISHED') {
    for (const p of after.players) if (!p.isAI) add(p.id, 'PLAY_GAME');
    for (const id of after.gameState.winnerIds) add(id, 'WIN_GAME');
  }
  for (const fact of facts) await system.missions.record(fact);
}
