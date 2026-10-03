import { useEffect, useRef, useState } from 'react';
import { Lobby, modeNames } from './Lobby';
import { Board, colors } from './Board';
import { useGame } from './useGame';
import { EventPanel } from './EventPanel';

export function App() {
  const game = useGame();
  const [showEvents, setShowEvents] = useState(false);
  const { view, lobby, connected, busy, error, leave, act } = game;
  const logEnd = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const logPanel = logEnd.current?.parentElement;
    if (logPanel) logPanel.scrollTop = logPanel.scrollHeight;
  }, [view?.room.gameState.revision]);
  const room = view?.room;
  const me = room?.players.find((p) => p.id === view?.you);
  const current = room?.players.find((p) => p.id === room.currentTurnPlayerId);
  const tile = me ? room?.gameState.tiles[me.position] : undefined;
  const active = !busy && connected;
  return (
    <main>
      <header>
        <a className="brand" href="/">
          ✦{' '}
          <span>
            별길 상회<small>STARLANE TRADERS</small>
          </span>
        </a>
        <div className="connection">
          <button className="secondary" onClick={() => setShowEvents(!showEvents)}>
            {showEvents ? '게임으로' : 'EVENT'}
          </button>
          <i className={connected ? 'online' : ''} />
          {connected ? '서버 연결됨' : '연결 중'}
        </div>
      </header>
      {error && (
        <div role="alert" className="error">
          {error}
        </div>
      )}
      {showEvents ? (
        <EventPanel
          data={game.events}
          active={active}
          action={game.eventAction}
          refresh={game.refreshEvents}
        />
      ) : !room ? (
        <Lobby {...game} active={active} />
      ) : (
        <>
          <div className="game-heading">
            <div>
              <span className="eyebrow">하늘섬 교역 지도</span>
              <h1>{room.status === 'FINISHED' ? '항해가 끝났습니다' : '오늘의 별길'}</h1>
            </div>
            <span>
              {room.players.length}인 대전 · {modeNames[room.mode]} · 방 {room.roomId}
            </span>
          </div>
          {lobby?.room?.paused && (
            <div role="status" className="error">
              연결이 끊긴 플레이어의 재접속을 기다립니다. 60초 후 AI가 이어받습니다.
            </div>
          )}
          <div className="game-layout">
            <div className="board-scroll">
              <Board room={room} diceSkin={game.events?.account.equipped.DICE_SKIN} />
            </div>
            <aside>
              <section className="panel">
                <span className="eyebrow">TRADERS</span>
                <h2>참가 상인</h2>
                <div className="players">
                  {room.players.map((p, i) => (
                    <div
                      key={p.id}
                      className={`player ${p.isBankrupt ? 'bankrupt' : ''} ${p.id === current?.id ? 'current' : ''}`}
                    >
                      <span className="player-number" style={{ background: colors[i] }}>
                        {i + 1}
                      </span>
                      <div>
                        <strong>
                          {p.nickname} {p.id === view.you ? '(나)' : ''}
                        </strong>
                        <small>
                          {p.isBankrupt
                            ? '파산'
                            : `${lobby?.room?.members.find((member) => member.playerId === p.id)?.control === 'AI' ? 'AI · ' : ''}도시 ${p.ownedTileIds.length}개`}
                        </small>
                      </div>
                      <b>
                        {p.money.toLocaleString()} <small>G</small>
                      </b>
                    </div>
                  ))}
                </div>
              </section>
              <section className="panel actions">
                <span className="eyebrow">YOUR MOVE</span>
                <h2>
                  {room.status === 'FINISHED'
                    ? `${room.players
                        .filter((p) => room.gameState.winnerIds.includes(p.id))
                        .map((p) => p.nickname)
                        .join(', ')} 승리!`
                    : me?.isBankrupt
                      ? '파산 · 남은 경기를 관전합니다'
                      : current?.id === view.you
                        ? '당신의 차례입니다'
                        : `${current?.nickname} 거래 중…`}
                </h2>
                <p>
                  내 위치: {tile?.name}
                  {tile?.type === 'CITY' ? ` · 현재 통행료 ${view.options.toll} G` : ''}
                </p>
                <div className="action-grid">
                  <button
                    disabled={!active || !view.options.canRoll}
                    onClick={() => act({ type: 'ROLL' })}
                  >
                    ⚄ 주사위 굴리기
                  </button>
                  <button
                    disabled={!active || !view.options.canBuy}
                    onClick={() => act({ type: 'BUY' })}
                  >
                    도시 구매 {tile?.type === 'CITY' ? `· ${tile.purchasePrice}` : ''}
                  </button>
                  <button
                    disabled={!active || !view.options.canUpgrade}
                    onClick={() => act({ type: 'UPGRADE' })}
                  >
                    건설 · {view.options.upgradePrice} G
                  </button>
                  <button
                    className="secondary"
                    disabled={!active || !view.options.canEndTurn}
                    onClick={() => act({ type: 'END_TURN' })}
                  >
                    턴 종료 →
                  </button>
                </div>
                {room.status === 'FINISHED' && (
                  <button disabled={!active} onClick={leave}>
                    로비로 돌아가기
                  </button>
                )}
                <button className="secondary" disabled={!active} onClick={leave}>
                  방 나가기{room.status === 'PLAYING' ? ' · AI가 이어받기' : ''}
                </button>
                <small>
                  구매·건설 후 현금을 남겨두세요. 120턴부터 유지비와 통행료가 상승합니다.
                </small>
              </section>
              <section className="panel">
                <span className="eyebrow">VOYAGE JOURNAL</span>
                <h2>거래 기록</h2>
                <div className="logs" role="log" aria-label="턴 로그">
                  {room.gameState.logs.map((log) => (
                    <p key={log.sequence}>
                      <span>T{log.turn}</span>
                      {log.message}
                    </p>
                  ))}
                  <div ref={logEnd} />
                </div>
              </section>
            </aside>
          </div>
        </>
      )}
      <footer>
        별길 상회 · 독자적인 하늘섬 보드게임 프로토타입{' '}
        <span>모든 게임 판정은 서버에서 처리됩니다.</span>
      </footer>
    </main>
  );
}
