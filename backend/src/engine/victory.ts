import { GameMode, type GameRoom } from '../../../shared/src/index.js';
export interface VictoryCondition {
  evaluate(room: Readonly<GameRoom>): string[] | null;
}
// Additional conditions (district monopoly, mission victory) can be injected here.
export class LastStandingVictory implements VictoryCondition {
  evaluate(room: Readonly<GameRoom>): string[] | null {
    const alive = room.players.filter((p) => !p.isBankrupt);
    if (alive.length === 1) return [alive[0]!.id];
    if (
      room.mode === GameMode.TWO_VS_TWO &&
      alive.length > 0 &&
      alive.every((p) => p.teamId === alive[0]!.teamId)
    ) {
      return room.players.filter((p) => p.teamId === alive[0]!.teamId).map((p) => p.id);
    }
    return null;
  }
}
