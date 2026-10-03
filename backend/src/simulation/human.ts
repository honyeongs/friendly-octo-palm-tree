import { createInterface } from 'node:readline/promises';
import { stdin, stdout } from 'node:process';
import { GameEngine } from '../engine/GameEngine.js';
import { AIService } from '../ai/AIService.js';
import type { GameAction } from '../../../shared/src/index.js';

const reader = createInterface({ input: stdin, output: stdout });
const inputClosed = new AbortController();
reader.once('close', () => inputClosed.abort());
const engine = new GameEngine('console-human');
engine.addPlayer({ id: 'human', nickname: '여행자' });
engine.addPlayer({ id: 'ai', nickname: 'AI_1', isAI: true });
engine.startGame();
const ai = new AIService();
const actions: Record<string, GameAction> = {
  r: { type: 'ROLL' },
  b: { type: 'BUY' },
  u: { type: 'UPGRADE' },
  e: { type: 'END_TURN' },
};
try {
  while (engine.getSnapshot().status === 'PLAYING') {
    const room = engine.getSnapshot();
    const id = room.currentTurnPlayerId!;
    const options = engine.getActionOptions(id);
    let action: GameAction;
    if (id === 'ai') action = ai.decide(room, options);
    else {
      const p = room.players.find((p) => p.id === id)!;
      console.log(
        `\nTurn ${room.turnNumber} · ${room.gameState.tiles[p.position]!.name} · 현금 ${p.money}`,
      );
      const commands = [
        options.canRoll ? 'r=주사위' : '',
        options.canBuy ? 'b=구매' : '',
        options.canUpgrade ? `u=건설(${options.upgradePrice})` : '',
        options.canEndTurn ? 'e=턴 종료' : '',
        'q=종료',
      ]
        .filter(Boolean)
        .join(' / ');
      const answer = (await reader.question(`${commands} > `, { signal: inputClosed.signal }))
        .trim()
        .toLowerCase();
      if (answer === 'q') break;
      const selected = actions[answer];
      if (!selected) {
        console.log('표시된 명령을 입력하세요.');
        continue;
      }
      action = selected;
    }
    try {
      engine
        .dispatch(id, action)
        .forEach((log) => console.log(`[Turn ${log.turn}] ${log.message}`));
    } catch (error) {
      console.error(error instanceof Error ? error.message : '행동 오류');
    }
  }
} catch (error) {
  if (!inputClosed.signal.aborted) {
    console.error(error instanceof Error ? error.message : '콘솔 대전 오류');
    process.exitCode = 1;
  }
} finally {
  reader.close();
}
