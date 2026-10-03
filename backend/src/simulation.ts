import { AIDifficulty } from '../../shared/src/index.js';
import { SIMULATION_CONFIG } from './config/simulation.js';
import { simulate, SimulationLimitError } from './simulation/match.js';
import { formatSummary } from './simulation/report.js';

function parseArguments(args: string[]) {
  const options = new Map<string, string>();
  const allowed = new Set(['--players', '--seed', '--difficulty', '--max-turns', '--max-actions']);
  let quiet = false;
  for (let i = 0; i < args.length; i++) {
    const key = args[i]!;
    if (key === '--quiet') {
      quiet = true;
      continue;
    }
    if (!allowed.has(key)) throw new Error(`알 수 없는 옵션: ${key}`);
    const value = args[++i];
    if (!value || value.startsWith('--')) throw new Error(`${key} 값이 필요합니다.`);
    options.set(key, value);
  }
  const count = Number(options.get('--players') ?? SIMULATION_CONFIG.players);
  const seed = Number(options.get('--seed') ?? SIMULATION_CONFIG.seed);
  const difficulty = (options.get('--difficulty') ?? AIDifficulty.NORMAL) as AIDifficulty;
  const maxTurns = Number(options.get('--max-turns') ?? SIMULATION_CONFIG.maxTurns);
  const maxActions = Number(options.get('--max-actions') ?? SIMULATION_CONFIG.maxActions);
  if (!Number.isSafeInteger(seed) || !Object.values(AIDifficulty).includes(difficulty))
    throw new Error('seed 또는 difficulty가 유효하지 않습니다.');
  return { count, seed, difficulty, maxTurns, maxActions, quiet };
}

try {
  const args = parseArguments(process.argv.slice(2));
  // Default is four AI players. The existing factory is shared with tests; no duplicate game loop.
  const room = simulate(
    args.count,
    args.seed,
    args.quiet ? undefined : (log) => console.log(`[Turn ${log.turn}] ${log.message}`),
    args.difficulty,
    args.maxActions,
    args.maxTurns,
  );
  console.log(formatSummary(room));
} catch (error) {
  if (error instanceof SimulationLimitError) console.error(formatSummary(error.room, error.reason));
  else console.error(error instanceof Error ? error.message : '시뮬레이션 오류');
  process.exitCode = 1;
}
