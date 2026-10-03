export interface Rules {
  startingMoney: number;
  startBonus: number;
  maxPlayers: number;
  upgradePriceRatios: readonly number[];
  tollMultipliers: readonly number[];
  eventAmounts: readonly number[];
  pressureStartsAt: number;
  pressureInterval: number;
  pressureTollIncrement: number;
  upkeepPerPressure: number;
  maxLogs: number;
}
export const DEFAULT_RULES: Rules = {
  startingMoney: 1600,
  startBonus: 180,
  maxPlayers: 4,
  upgradePriceRatios: [0.5, 0.8, 1.2],
  tollMultipliers: [1, 2, 4, 7],
  eventAmounts: [-140, -80, 60, 100, 160],
  pressureStartsAt: 120,
  pressureInterval: 32,
  pressureTollIncrement: 0.3,
  upkeepPerPressure: 45,
  maxLogs: 240,
};
