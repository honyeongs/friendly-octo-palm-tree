import { Prisma, PrismaClient } from '@prisma/client';
import type { EventAccount } from './EventTypes.js';
import { emptyAccount, type EventRepository } from './EventRepository.js';
export class PrismaEventRepository implements EventRepository {
  constructor(private readonly db: PrismaClient) {}
  async read(userId: string): Promise<EventAccount> {
    const row = await this.db.eventAccount.findUnique({ where: { userId } });
    return row ? (row.state as unknown as EventAccount) : emptyAccount(userId);
  }
  async transaction<T>(userId: string, update: (account: EventAccount) => T): Promise<T> {
    for (let attempt = 0; attempt < 5; attempt++) {
      try {
        return await this.db.$transaction(
          async (tx) => {
            await tx.eventAccount.upsert({
              where: { userId },
              create: { userId, state: emptyAccount(userId) as unknown as Prisma.InputJsonValue },
              update: {},
            });
            await tx.$queryRaw`SELECT "userId" FROM "EventAccount" WHERE "userId" = ${userId} FOR UPDATE`;
            const row = await tx.eventAccount.findUniqueOrThrow({ where: { userId } });
            const account = row.state as unknown as EventAccount;
            const result = update(account);
            await tx.eventAccount.update({
              where: { userId },
              data: {
                state: account as unknown as Prisma.InputJsonValue,
                revision: { increment: 1 },
              },
            });
            return result;
          },
          { isolationLevel: Prisma.TransactionIsolationLevel.Serializable },
        );
      } catch (error) {
        if (
          !(error instanceof Prisma.PrismaClientKnownRequestError) ||
          !['P2034', 'P2002'].includes(error.code) ||
          attempt === 4
        )
          throw error;
      }
    }
    throw new Error('이벤트 저장 충돌을 재시도하세요.');
  }
}
