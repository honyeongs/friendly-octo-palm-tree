import 'dotenv/config';
import { createApp } from './app.js';
import { resolve } from 'node:path';
import { PrismaClient } from '@prisma/client';
import { LocalEventRepository } from '../features/events/EventRepository.js';
import { PrismaEventRepository } from '../features/events/PrismaEventRepository.js';
import { createEventSystem } from '../features/events/index.js';
const port = Number(process.env.PORT ?? 3001);
if (!Number.isInteger(port) || port < 1 || port > 65535)
  throw new Error('PORT는 1~65535 사이여야 합니다.');
const dataDirectory = resolve(process.env.DATA_DIRECTORY ?? '.data');
const prisma = process.env.EVENT_STORAGE === 'postgres' ? new PrismaClient() : null;
const repository = prisma
  ? new PrismaEventRepository(prisma)
  : new LocalEventRepository(resolve(dataDirectory, 'accounts'));
const eventSystem = createEventSystem(repository);
await eventSystem;
const app = createApp({
  origin: process.env.CLIENT_ORIGIN,
  identityFile: resolve(dataDirectory, 'identities.json'),
  eventSystem,
});
app.httpServer.on('error', (error) => {
  console.error('Server error:', error.message);
  process.exitCode = 1;
});
app.httpServer.listen(port, '127.0.0.1', () =>
  console.log(`별길 상회 server: http://localhost:${port}`),
);
for (const signal of ['SIGINT', 'SIGTERM'] as const)
  process.once(signal, () => {
    void app.close().finally(() => prisma?.$disconnect());
  });
