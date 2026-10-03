import { useState } from 'react';
import {
  AIDifficulty,
  GameMode,
  type CreateRoomInput,
  type LobbyView,
} from '../../shared/src/index';
export const modeNames = {
  SOLO_AI: 'AI 대전',
  ONE_VS_ONE: '온라인 1vs1',
  TWO_VS_TWO: '온라인 2vs2',
  FOUR_PLAYER_FFA: '온라인 4인 개인전',
};
interface Props {
  lobby: LobbyView | null;
  active: boolean;
  create: (input: CreateRoomInput) => void;
  join: (code: string, nickname: string) => void;
  ready: (value: boolean) => void;
  start: () => void;
  leave: () => void;
}
export function Lobby({ lobby, active, create, join, ready, start, leave }: Props) {
  const [nickname, setNickname] = useState('여행자');
  const [mode, setMode] = useState(GameMode.ONE_VS_ONE);
  const [aiCount, setAICount] = useState(3);
  const [difficulty, setDifficulty] = useState(AIDifficulty.NORMAL);
  const [code, setCode] = useState('');
  const room = lobby?.room;
  if (room) {
    const me = room.members.find((p) => p.playerId === lobby.you);
    const host = room.hostPlayerId === lobby.you;
    const canStart =
      room.members.length >= 2 &&
      (room.mode === GameMode.SOLO_AI || room.members.length === room.capacity) &&
      room.members.every((p) => p.ready && p.connected);
    return (
      <section className="waiting-room panel">
        <span className="eyebrow">WAITING ROOM</span>
        <h1>{modeNames[room.mode]} 대기방</h1>
        <p>아래 방 코드를 상대에게 알려주세요.</p>
        <output className="room-code" aria-label="방 코드">
          {room.roomId}
        </output>
        <p>
          {room.members.length} / {room.capacity}명 · 모두 준비하면 방장이 시작합니다.
        </p>
        <div className="players">
          {room.members.map((p, i) => (
            <div className="player" key={p.playerId}>
              <span className="player-number">{i + 1}</span>
              <div>
                <strong>
                  {p.nickname} {p.playerId === room.hostPlayerId ? '· 방장' : ''}
                  {p.playerId === lobby.you ? ' (나)' : ''}
                </strong>
                <small>
                  {!p.connected ? '재접속 대기 중' : p.ready ? '준비 완료' : '준비 전'}
                  {room.mode === GameMode.TWO_VS_TWO ? ` · 팀 ${(i % 2) + 1}` : ''}
                </small>
              </div>
            </div>
          ))}
        </div>
        <div className="action-grid">
          <button disabled={!active} onClick={() => ready(!me?.ready)}>
            {me?.ready ? '준비 취소' : '준비하기'}
          </button>
          {host && (
            <button disabled={!active || !canStart} onClick={start}>
              게임 시작
            </button>
          )}
          <button className="secondary" disabled={!active} onClick={leave}>
            방 나가기
          </button>
        </div>
        <small>
          인원이 바뀌면 준비 상태가 초기화됩니다. 새로고침 후 60초 안에 같은 세션으로 복귀할 수
          있습니다.
        </small>
      </section>
    );
  }
  return (
    <section className="lobby">
      <div>
        <span className="eyebrow">함께 떠나는 하늘섬 교역</span>
        <h1>
          같은 별길에서
          <br />
          <em>친구와 겨뤄보세요.</em>
        </h1>
        <p>
          방을 만들고 코드를 공유하세요.
          <br />두 상인부터 네 상인까지, 하나의 보드에서 만납니다.
        </p>
        <div className="lobby-art">
          ✦<span>32 TILES / UP TO 4 TRADERS</span>
        </div>
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          create({ nickname, mode, aiCount, difficulty });
        }}
      >
        <span className="eyebrow">새로운 항해</span>
        <h2>상회 개설 / 입장</h2>
        <label>
          상인 이름
          <input
            value={nickname}
            maxLength={20}
            required
            onChange={(e) => setNickname(e.target.value)}
          />
        </label>
        <label>
          대전 방식
          <select value={mode} onChange={(e) => setMode(e.target.value as GameMode)}>
            {Object.values(GameMode).map((value) => (
              <option key={value} value={value}>
                {modeNames[value]}
              </option>
            ))}
          </select>
        </label>
        {mode === GameMode.SOLO_AI && (
          <>
            <label>
              AI 상대
              <select value={aiCount} onChange={(e) => setAICount(Number(e.target.value))}>
                {[1, 2, 3].map((n) => (
                  <option key={n} value={n}>
                    {n}명
                  </option>
                ))}
              </select>
            </label>
            <label>
              AI 난이도
              <select
                value={difficulty}
                onChange={(e) => setDifficulty(e.target.value as AIDifficulty)}
              >
                {Object.values(AIDifficulty).map((d) => (
                  <option key={d}>{d}</option>
                ))}
              </select>
            </label>
          </>
        )}
        <button disabled={!active || !nickname.trim()} type="submit">
          {mode === GameMode.SOLO_AI ? 'AI 대전 시작' : '방 만들기'}
        </button>
        <label>
          참가할 방 코드
          <input
            aria-label="참가할 방 코드"
            value={code}
            maxLength={8}
            placeholder="8자리 방 코드"
            onChange={(e) => setCode(e.target.value.toUpperCase())}
          />
        </label>
        <button
          className="secondary"
          type="button"
          disabled={!active || !nickname.trim() || code.trim().length !== 8}
          onClick={() => join(code, nickname)}
        >
          방 입장
        </button>
        <small>
          브라우저 탭마다 별도의 플레이어 세션을 사용합니다.
          <br />
          서버를 재시작하면 현재 방과 경기는 초기화됩니다.
        </small>
      </form>
    </section>
  );
}
