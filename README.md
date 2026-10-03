# 별길 상회

가상의 하늘섬 도시를 거래하는 독자적인 32칸 보드게임. React + TypeScript + Vite / Node.js + Socket.IO / PostgreSQL + Prisma, npm workspaces.

## 현재 완료 상태

최우선 목표인 **서버 GameEngine만 사용하는 AI 4인 대전의 정상 종료**를 검증했습니다. 게임 엔진과 AI는 Socket.IO·PostgreSQL 없이 실행됩니다. 웹에서는 인간 1명 + AI 1~3명으로 플레이할 수 있습니다.

```text
frontend/src/       React 보드, 로비, 조작 버튼, 소켓 훅
backend/src/
  config/          보드·게임 규칙·AI 판단 수치·서버 제한
  engine/          GameEngine, 주입 가능한 승리 조건 및 RNG
  ai/              EASY / NORMAL / HARD 평가와 공통 행동 선택
  simulation/      AI 자동 대전, 콘솔 Human vs AI
  simulation.ts    npm run simulate 진입점 (기본 AI 4인)
  server/          Socket.IO 세션과 런타임 입력 검증
backend/tests/     엔진·AI 완주·소켓 통합 테스트
backend/prisma/    스키마 및 초기 PostgreSQL 마이그레이션
shared/src/        Player / Tile / GameRoom / GameAction / Socket 계약
```

## 검증 결과 (2026-09-11)

- TypeScript strict 검사 통과.
- Vitest **41개 테스트 통과**. 기존 규칙/소켓 테스트에 시뮬레이션 결과, 파산 순서 보존, 최대 턴/행동 제한과 경계 종료 테스트 추가.
- EASY/NORMAL/HARD × 2인/4인 × seed 0~19: **120경기 모두 생존 승리로 종료**, 현금 및 소유권 일관성 검증.
- 실제 시뮬레이션 CLI: `--players 4 --seed 42 --quiet` → **136턴, AI_3 승리**.
- 프론트·서버 빌드 성공, Prisma Client 생성 성공. npm 감사 취약점 **0건**. Prisma/Client는 감사 결과에 따라 6.12.0으로 동일하게 고정.
- 브라우저에서 로비 연결, 주사위/이동, 구매, 건설, 현금/통행료 변화 및 AI 턴 진행 확인.
- 콘솔 Human vs AI에서 실제 입력으로 인간 주사위 → 턴 종료 → AI 구매/건설 → 인간 차례 복귀 및 `q` 종료 확인. 입력 스트림 종료도 정상 처리.
- `prisma validate` 및 스키마로 생성한 SQL과 초기 마이그레이션의 일치 확인. 빌드된 Node 서버 단독 시작 확인.
- PostgreSQL 스키마와 초기 SQL은 제공하지만, 현재 PC에 Docker/PostgreSQL 실행 환경이 없어 **실제 DB 마이그레이션 적용은 검증하지 않았습니다**. 게임은 DB 없이 실행됩니다.

이 PC에는 Node 실행기는 있으나 npm 명령이 없어 프로젝트 내부 `.tools`에 npm을 준비했습니다. 현재 작업 폴더에서는 `scripts\npm-local.cmd test`, `scripts\npm-local.cmd run dev`, `scripts\npm-local.cmd run simulate -- --players 4 --seed 42`로 실행할 수 있습니다. `.tools`는 배포/버전 관리에서 제외되며 다른 PC에서는 Node.js와 함께 설치한 일반 npm을 사용하세요.

## 단계별 진행 기록

### 엔진·시뮬레이션 보완 — 이번 단계

- 기존 분석: `GameEngine`은 이미 React/Socket.IO/Prisma 의존 없이 실행되었고, 인간과 AI 모두 `dispatch(playerId, GameAction)`을 사용했습니다. 이를 유지하고 전면 재작성하지 않았습니다.
- 구현: 엔진 내부 메서드를 `rollDice`, `movePlayer`, `resolveTile`, `buyProperty`, `upgradeProperty`, `payToll`, `handleBankruptcy`, `nextTurn`, `checkWinner`로 정리했습니다. 통행료와 파산 처리를 분리하고, 이벤트/유지비/통행료의 현금 지급은 기존 공통 `pay`를 재사용합니다.
- 상태 변경: 위 메서드는 **private**입니다. 외부 컨트롤러는 생성/시작 이후 `dispatch`만 사용하므로 규칙 검증을 우회할 수 없습니다. AI의 판단 및 결과 출력은 snapshot을 읽기만 합니다. 주입 가능한 승리 조건도 복사본을 받습니다.
- 파산 순서: `gameState.bankruptcyOrder`에 엔진이 한 번씩 기록합니다. 화면 로그 240개 제한과 무관하게 유지되며, 출력 코드가 로그 문장을 해석하거나 상태를 변경하지 않습니다.
- 실행 경로: `backend/src/simulation.ts` → `simulation/match.ts`의 공통 생성/실행 루프. 기존 `simulation/run.ts`는 제거하여 CLI 중복을 없앴습니다. 기본 AI 4명을 생성하며 기존 2인·난이도·seed 옵션도 유지합니다.
- 종료 출력: 승자, 총 턴 수, 각 플레이어 최종 자금·소유 도시, 파산 순서를 출력합니다. 파산자의 도시는 기존 규칙대로 은행에 반환되므로 **최종 소유 도시는 없음**입니다.
- 안전 제한: `config/simulation.ts` 기본값은 **최대 2,000턴 / 20,000행동**입니다. 전체 플레이어의 개별 턴을 세며 휴식 턴도 포함합니다. 엔진의 `nextTurn` 내부에서도 확인하므로 연속 휴식/유지비 파산 전환이 한도를 넘지 않습니다. 지정한 마지막 턴/행동에서 정상 승리하면 승리가 우선합니다.
- 제한 도달: 현재 상태 요약과 `MAX_TURNS` 또는 `MAX_ACTIONS`를 출력하고 종료 코드 **1**로 중단합니다. 임의 승자나 정상 게임 종료로 표시하지 않습니다. 정상 완료 종료 코드는 **0**입니다.
- 미구현: 온라인 다인 입장·매칭·저장·새 승리 규칙은 이번 단계에서 추가하지 않았습니다.
- 테스트: `npm test`, `npm run typecheck`, `npm run build -w backend`.

```sh
npm run simulate
npm run simulate -- --quiet
npm run simulate -- --seed 42 --max-turns 2000 --max-actions 20000
npm run simulate -- --max-turns 1 --quiet
```

마지막 명령은 중단 동작 검증용이며 종료 코드 1과 승자 없음이 정상입니다. `--quiet`는 턴별 로그만 숨기고 최종 요약은 항상 표시합니다.

기본 seed 42의 검증된 결과:

```text
승자: AI_3
총 턴 수: 136
AI_1 | 최종 자금: 0 G | 소유 도시: 없음 | 파산
AI_2 | 최종 자금: 0 G | 소유 도시: 없음 | 파산
AI_3 | 최종 자금: 351 G | 소유 도시: 새벽항, 물결마루, 청옥부두, 빛고래섬, 수정계곡
AI_4 | 최종 자금: 0 G | 소유 도시: 없음 | 파산
파산 순서: 1. AI_1 → 2. AI_4 → 3. AI_2
```

### 1단계 — 기본 구조

- 구현: frontend/backend/shared 분리, 엄격한 TypeScript 설정, 공통 게임/Socket 계약, Prisma 스키마, PostgreSQL Compose 설정.
- 미구현: 게임 엔진, AI, 시뮬레이션, 화면 및 서버 연결은 다음 단계에서 추가.
- 실행: Node.js 22.12 이상, `npm install`. DB 설정은 `backend/.env.example`을 `backend/.env`로 복사 후 `docker compose up -d`, `npm run db:generate`, `npm run db:migrate -- --name init`.
- 검증: `npm run typecheck`, 이후 단계에서 `npm test` 추가.

온라인 사용자 인증/매칭/영속 저장은 이번 단계의 범위 밖이며 DB 없이도 엔진 및 시뮬레이션을 실행할 수 있도록 구성합니다.

### 2단계 — 독립 엔진

- 구현: 플레이어 생성, 시작/턴/주사위/이동/출항 보너스/특수칸, 구매, 3단계 건설(최종 랜드마크), 통행료, 파산, 개인 및 팀 생존 승리. 독점 승리는 `VictoryCondition` 주입으로 확장.
- 미구현: 대출/자산 매각, 더블 보너스, 독점 승리의 구체 규칙, RP 정산.
- 실행: `GameEngine`을 생성하고 `addPlayer`, `startGame`, `dispatch(playerId, action)` 호출. Socket.IO/DB 의존 없음.
- 테스트: `npm test` (회귀 테스트는 다음 시뮬레이션 단계에서 작성).
- 규칙: 구매/건설 후 현금 1 이상을 남겨야 함. 강제 지불 후 0이면 파산, 실제 보유 현금만 지급하고 도시는 은행에 반환. 자신의 도시에 도착했을 때 턴당 건설 1회, 구매 직후 건설 가능. 휴식칸은 다음 자기 턴 1회 건너뜀. 이동칸은 전방 이동하며 시작점 통과 보너스 적용.
- 장기전: 전체 행동 턴 120부터 32턴마다 압박 단계 상승. 통행료 +30%/단계, 자기 턴 시작 유지비 45/단계. 이 수치들은 `backend/src/config/rules.ts`에서 조절.

### 3단계 — 규칙 기반 AI

- 구현: 현금 유보, 가격 대비 통행료 및 동일 구역 소유 비율 평가, 건설 비용/수익 평가. EASY는 일부 매수/건설 생략, NORMAL은 기본 평가, HARD는 상대 위치와 2개 주사위 합 확률을 더함.
- 미구현: HARD의 다중 턴 예측, 이벤트 이동 확률 보정, 협력 전략/학습 AI. `StrategyEvaluator` 구현 주입으로 확장 가능.
- 실행: 엔진의 snapshot과 action options를 `AIService.decide`에 전달한 뒤 반환 행동을 `dispatch`로 실행.
- 테스트: `npm test`에서 난이도별 자동 완주와 현금 유보 검증.

### 4단계 — 로컬 시뮬레이션

- 구현: AI 2인, AI 4인, 콘솔 Human vs AI, seed 재현, 턴별 로그 및 종료 요약. 행동 안전 한도 초과 시 실패 종료.
- 미구현: 콘솔 저장/불러오기.
- 실행: `npm run simulate -- --players 4 --seed 42`, `npm run simulate -- --players 2 --difficulty HARD`, `npm run play:console`. 로그 생략은 `--quiet`.
- 테스트: `npm test`. DB나 Socket.IO 없이 엔진만으로 실행.

### 5단계 — 서버 연결 및 최소 화면

- 구현: Socket.IO Human vs AI(상대 1~3명), 32칸 사각 보드, 말/소유/건설 단계, 현재 턴/현금/주사위, 서버가 허용한 구매/건설/종료 버튼, 기록, 연결/오류/승리 화면. AI 파산 이후에도 남은 대전 자동 진행.
- 서버 검증: 런타임 입력 검증, 소켓에 바인딩된 신원, revision을 통한 중복/오래된 요청 방지, 요청 빈도/방 수/패킷 크기 제한. AI 한 행동마다 비동기 스케줄링하고 연결 종료 시 타이머/방 정리.
- 미구현: 여러 인간의 방 입장, 인증, 자동 매칭, 연결 복구, 관전자 입장, DB 영속 저장. 1vs1/2vs2/FFA 엔진 모드는 준비되어 있으나 웹 로비는 SOLO_AI만 노출.
- 실행: 루트 `npm run dev`, 브라우저에서 http://localhost:5173 접속. `npm run build`, `npm run start -w backend`로 빌드 서버 실행. 프론트 결과물은 `frontend/dist`이며 배포 시 동일 origin의 `/socket.io`를 backend에 프록시해야 함.
- 테스트: `npm run typecheck`, `npm test`, `npm run build`. 웹에서는 주사위 → 구매/건설(가능한 칸) → 턴 종료 순서로 조작.

## 구조 및 확장 경계

`shared/src`는 데이터/행동/통신 계약, `backend/src/engine`은 게임 판정, `ai`는 행동 선택, `server`는 연결 및 세션, `simulation`은 엔진 실행 어댑터입니다. 클라이언트가 전달하는 주사위/금액/소유자 정보는 사용하지 않습니다. 엔진 snapshot은 깊은 복사이므로 외부 변경이 내부 상태에 영향을 주지 않습니다. 테스트와 시뮬레이션은 seeded RNG를 주입하고 실제 서버는 Node crypto RNG를 사용합니다.

향후 매칭 서비스가 인원과 팀을 구성하고 컨트롤러가 `GameAction`을 생성하게 하면 기존 엔진을 재사용할 수 있습니다. `Match` Prisma 모델은 snapshot/revision 저장의 기본 계약일 뿐 현재 실시간 경기는 메모리에만 있습니다. 실제 서비스 전에는 인증/복구, 방별 명령 큐 및 저장 트랜잭션, 다중 서버 소유권, 관측/운영 구성을 구현해야 합니다. RP는 필드/기본값만 있으며 랭킹 변화는 없습니다.

## 기본 실행 순서

```sh
npm install
npm test
npm run simulate -- --players 4 --seed 42
npm run dev
```

DB 사용 준비(엔진 실행에는 불필요): `.env.example` 복사 후 `docker compose up -d`, `npm run db:generate`, `npm run db:migrate -- --name init`. 개발용 DB 계정은 배포에서 변경해야 합니다. 서버 기본값은 127.0.0.1:3001, 허용 웹 origin은 http://localhost:5173입니다. Vite 포트가 바뀌면 CLIENT_ORIGIN도 맞추세요.
