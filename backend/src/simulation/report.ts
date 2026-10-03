import type { GameRoom } from '../../../shared/src/index.js';

// Presentation only: outcomes and ownership are read exclusively from the engine snapshot.
export function summarize(room: GameRoom) {
  return {
    winners: room.gameState.winnerIds.map((id) => room.players.find((p) => p.id === id)!.nickname),
    totalTurns: room.turnNumber,
    players: room.players.map((player) => ({
      id: player.id,
      nickname: player.nickname,
      money: player.money,
      ownedCities: room.gameState.tiles
        .filter((tile) => tile.ownerId === player.id)
        .map((tile) => tile.name),
      isBankrupt: player.isBankrupt,
    })),
    bankruptcyOrder: room.gameState.bankruptcyOrder.map(
      (id) => room.players.find((p) => p.id === id)!.nickname,
    ),
  };
}
export function formatSummary(room: GameRoom, reason?: string): string {
  const summary = summarize(room);
  return [
    `\n=== ${reason ? `시뮬레이션 중단: ${reason}` : '게임 종료'} ===`,
    `승자: ${summary.winners.join(', ') || '없음 (미종료)'}`,
    `총 턴 수: ${summary.totalTurns}`,
    ...summary.players.map(
      (p) =>
        `${p.nickname} | 최종 자금: ${p.money} G | 소유 도시: ${p.ownedCities.join(', ') || '없음'}${p.isBankrupt ? ' | 파산' : ''}`,
    ),
    `파산 순서: ${summary.bankruptcyOrder.map((name, i) => `${i + 1}. ${name}`).join(' → ') || '없음'}`,
  ].join('\n');
}
