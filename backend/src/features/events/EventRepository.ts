import { mkdirSync, readFileSync, existsSync, renameSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import type { EventAccount } from './EventTypes.js';
export const emptyAccount = (userId: string): EventAccount => ({
  userId,
  currencies: {},
  coins: 0,
  boxes: {},
  inventory: {},
  equipped: {},
  purchases: {},
  missions: {},
  attendance: {},
  claims: [],
  processedFacts: [],
  participation: {},
  history: [],
});
export interface EventRepository {
  read(userId: string): Promise<EventAccount>;
  transaction<T>(userId: string, update: (account: EventAccount) => T): Promise<T>;
}
// Local single-process adapter. Atomic file replacement and a queue prevent double-spend.
// PostgreSQL adapter uses a database row lock for multiple application processes.
export class LocalEventRepository implements EventRepository {
  private readonly accounts = new Map<string, EventAccount>();
  private tail: Promise<unknown> = Promise.resolve();
  constructor(private readonly directory?: string) {
    if (directory) mkdirSync(directory, { recursive: true });
  }
  async read(userId: string): Promise<EventAccount> {
    await this.tail;
    return structuredClone(this.load(userId));
  }
  transaction<T>(userId: string, update: (account: EventAccount) => T): Promise<T> {
    const result = this.tail.then(() => {
      const account = structuredClone(this.load(userId));
      const value = update(account);
      if (this.directory) {
        const path = this.path(userId);
        writeFileSync(`${path}.tmp`, JSON.stringify(account));
        renameSync(`${path}.tmp`, path);
      }
      this.accounts.set(userId, account);
      return structuredClone(value);
    });
    this.tail = result.then(
      () => undefined,
      () => undefined,
    );
    return result;
  }
  private path(id: string): string {
    if (!/^[a-zA-Z0-9_-]{1,100}$/.test(id)) throw new Error('유효하지 않은 사용자 ID입니다.');
    return join(this.directory!, `${id}.json`);
  }
  private load(id: string): EventAccount {
    let account = this.accounts.get(id);
    if (!account && this.directory && existsSync(this.path(id)))
      account = JSON.parse(readFileSync(this.path(id), 'utf8')) as EventAccount;
    return account ?? emptyAccount(id);
  }
}
