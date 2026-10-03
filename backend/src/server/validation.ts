import {
  AIDifficulty,
  GameMode,
  type ActionRequest,
  type CreateRoomInput,
} from '../../../shared/src/index.js';
function record(value: unknown): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value))
    throw new Error('올바른 요청 객체가 필요합니다.');
  return value as Record<string, unknown>;
}
function nickname(value: unknown): string {
  if (typeof value !== 'string' || !value.trim() || value.trim().length > 20)
    throw new Error('닉네임은 1~20자여야 합니다.');
  return value.trim();
}
export function parseCreate(input: unknown): Required<CreateRoomInput> {
  const data = record(input);
  if (!Object.values(GameMode).includes(data.mode as GameMode))
    throw new Error('올바른 게임 모드가 필요합니다.');
  const aiCount = data.aiCount ?? 1;
  const difficulty = data.difficulty ?? AIDifficulty.NORMAL;
  if (
    !Number.isInteger(aiCount) ||
    Number(aiCount) < 1 ||
    Number(aiCount) > 3 ||
    !Object.values(AIDifficulty).includes(difficulty as AIDifficulty)
  )
    throw new Error('AI 수 또는 난이도가 올바르지 않습니다.');
  return {
    nickname: nickname(data.nickname),
    mode: data.mode as GameMode,
    aiCount: Number(aiCount),
    difficulty: difficulty as AIDifficulty,
  };
}
export function parseJoin(input: unknown) {
  const data = record(input);
  if (typeof data.roomId !== 'string' || !/^[A-Z0-9]{8}$/.test(data.roomId.trim().toUpperCase()))
    throw new Error('8자리 방 코드를 확인하세요.');
  return { roomId: data.roomId.trim().toUpperCase(), nickname: nickname(data.nickname) };
}
export function parseReady(input: unknown): boolean {
  const data = record(input);
  if (typeof data.ready !== 'boolean') throw new Error('준비 상태는 true 또는 false여야 합니다.');
  return data.ready;
}
export function parseAction(input: unknown): ActionRequest {
  const data = record(input);
  if (
    typeof data.roomId !== 'string' ||
    data.roomId.length !== 8 ||
    !Number.isSafeInteger(data.expectedRevision) ||
    Number(data.expectedRevision) < 0
  )
    throw new Error('유효하지 않은 행동 요청입니다.');
  // Only accept routing/revision. money, position, diceResult, playerId and action are never read.
  return { roomId: data.roomId, expectedRevision: Number(data.expectedRevision) };
}
