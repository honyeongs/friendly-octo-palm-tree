export * from '../../../../shared/src/events.js';
export type ServerClock = () => Date;
export interface GameFact {
  id: string;
  userId: string;
  target: import('./EventTypes.js').MissionTarget;
  occurredAt: string;
}
