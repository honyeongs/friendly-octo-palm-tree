import { createHash, randomBytes, randomUUID } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';
export interface PlayerSession {
  playerId: string;
  token: string;
  socketId: string | null;
}
export class SessionStore {
  private readonly sessions = new Map<string, PlayerSession>();
  private readonly identities: Map<string, string>;
  constructor(private readonly identityFile?: string) {
    this.identities = new Map(
      identityFile && existsSync(identityFile)
        ? Object.entries(JSON.parse(readFileSync(identityFile, 'utf8')) as Record<string, string>)
        : [],
    );
  }
  connect(token: unknown, socketId: string): PlayerSession {
    if (token !== undefined && (typeof token !== 'string' || !/^[a-f0-9]{64}$/.test(token)))
      throw new Error('INVALID_SESSION');
    let session = typeof token === 'string' ? this.sessions.get(token) : undefined;
    if (!session && typeof token === 'string') {
      const playerId = this.identities.get(this.hash(token));
      if (playerId) session = { playerId, token, socketId: null };
    }
    if (typeof token === 'string' && !session) throw new Error('SESSION_EXPIRED');
    if (session?.socketId) throw new Error('SESSION_IN_USE');
    if (!session) {
      session = { playerId: randomUUID(), token: randomBytes(32).toString('hex'), socketId };
      this.identities.set(this.hash(session.token), session.playerId);
      if (this.identityFile) {
        mkdirSync(dirname(this.identityFile), { recursive: true });
        writeFileSync(
          `${this.identityFile}.tmp`,
          JSON.stringify(Object.fromEntries(this.identities)),
        );
        renameSync(`${this.identityFile}.tmp`, this.identityFile);
      }
    }
    this.sessions.set(session.token, session);
    session.socketId = socketId;
    return session;
  }
  disconnect(session: PlayerSession, socketId: string): boolean {
    if (session.socketId !== socketId) return false;
    session.socketId = null;
    return true;
  }
  expire(session: PlayerSession): void {
    if (!session.socketId) this.sessions.delete(session.token);
  }
  clear(): void {
    this.sessions.clear();
  }
  private hash(token: string): string {
    return createHash('sha256').update(token).digest('hex');
  }
}
