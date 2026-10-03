import { createServer } from 'node:http';
import { Server } from 'socket.io';
import { createEventSystem, type EventSystem } from '../features/events/index.js';
import { EventController } from '../features/events/EventController.js';
import { recordMatchChange } from '../features/events/GameEventBridge.js';
import { SocketHandler, type GameServer, type HandlerOptions } from './SocketHandler.js';
import { SERVER_CONFIG } from '../config/server.js';

export function createApp(
  options: HandlerOptions & { origin?: string; eventSystem?: Promise<EventSystem> } = {},
) {
  const httpServer = createServer((req, res) => {
    if (req.url === '/health' && req.method === 'GET') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ status: 'ok', persistence: 'in-memory' }));
    } else {
      res.writeHead(404);
      res.end('Not found');
    }
  });
  const origin = options.origin ?? 'http://localhost:5173';
  const io: GameServer = new Server(httpServer, {
    cors: { origin },
    maxHttpBufferSize: SERVER_CONFIG.maxPayloadBytes,
    allowRequest: (req, callback) =>
      callback(null, !req.headers.origin || req.headers.origin === origin),
  });
  const system = options.eventSystem ?? createEventSystem();
  void system.catch((error) => console.error('Event config failed', error));
  const eventTasks = new Set<Promise<void>>();
  const handler = new SocketHandler(io, {
    ...options,
    onMatchChange: (change, ids) => {
      options.onMatchChange?.(change, ids);
      const task = system
        .then((s) => recordMatchChange(s, change, ids))
        .catch((error) => console.error('Event mission update failed', error));
      eventTasks.add(task);
      void task.then(() => eventTasks.delete(task));
    },
  });
  const events = new EventController(system);
  io.on('connection', (socket) => events.attach(socket));
  const close = async () => {
    handler.close();
    await Promise.all(eventTasks);
    await new Promise<void>((resolve) => io.close(() => resolve()));
  };
  return { httpServer, io, close };
}
