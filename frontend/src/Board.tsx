import type { GameRoom } from '../../shared/src/index';
export const colors = ['#2dd4bf', '#fbbf24', '#c084fc', '#fb7185'];
function coordinate(index: number): { gridRow: number; gridColumn: number } {
  if (index <= 8) return { gridRow: 9, gridColumn: 9 - index };
  if (index <= 16) return { gridRow: 17 - index, gridColumn: 1 };
  if (index <= 24) return { gridRow: 1, gridColumn: index - 15 };
  return { gridRow: index - 23, gridColumn: 9 };
}
export function Board({ room, diceSkin }: { room: GameRoom; diceSkin?: string }) {
  const current = room.players.find((p) => p.id === room.currentTurnPlayerId);
  return (
    <div className="board" aria-label="32칸 별길 보드">
      {room.gameState.tiles.map((tile) => {
        const ownerIndex = room.players.findIndex((p) => p.id === tile.ownerId);
        const tokens = room.players.filter((p) => !p.isBankrupt && p.position === tile.index);
        return (
          <div
            key={tile.id}
            className={`tile ${tile.type.toLowerCase()} ${current?.position === tile.index ? 'active-tile' : ''}`}
            style={{
              ...coordinate(tile.index),
              borderTopColor: ownerIndex >= 0 ? colors[ownerIndex] : undefined,
            }}
            title={`${tile.index} · ${tile.name} · 소유: ${room.players[ownerIndex]?.nickname ?? '없음'} · 기본 통행료 ${tile.baseToll}`}
          >
            <span className="tile-index">{String(tile.index).padStart(2, '0')}</span>
            <strong>{tile.name}</strong>
            <span className="tile-price">
              {tile.type === 'CITY'
                ? `${tile.purchasePrice} G`
                : {
                    START: '출항 보너스',
                    EVENT: '바람 소식',
                    REST: '1턴 휴식',
                    TRAVEL: '순풍 이동',
                  }[tile.type]}
            </span>
            {tile.ownerId && (
              <span className="building">
                {tile.buildingLevel === 3
                  ? '◆ 랜드마크'
                  : tile.buildingLevel
                    ? '▰'.repeat(tile.buildingLevel)
                    : '빈 부지'}
              </span>
            )}
            <div className="tokens">
              {tokens.map((p) => (
                <span
                  key={p.id}
                  className="token"
                  style={{
                    background: colors[room.players.findIndex((other) => other.id === p.id)],
                  }}
                  title={p.nickname}
                >
                  {room.players.findIndex((other) => other.id === p.id) + 1}
                </span>
              ))}
            </div>
          </div>
        );
      })}
      <div className="board-center">
        <span className="eyebrow">STARLANE TRADERS</span>
        <h2>
          별길을 따라,
          <br />
          나만의 상회를.
        </h2>
        <p>
          구름 너머 도시를 만나고
          <br />
          당신의 랜드마크를 세워보세요.
        </p>
        <div
          className="dice"
          data-skin={diceSkin}
          aria-label={`주사위 ${room.gameState.dice?.join(', ') ?? '대기'}`}
        >
          {(room.gameState.dice ?? ['?', '?']).map((d, i) => (
            <span key={i}>{d}</span>
          ))}
        </div>
        <span className="turn-badge">
          TURN {room.turnNumber} · {current?.nickname}
        </span>
        <small>32개의 길 · 하나의 승자</small>
      </div>
    </div>
  );
}
