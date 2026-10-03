import { readdir } from 'node:fs/promises';
import type { EventDefinition } from '../EventTypes.js';
export async function loadEventConfigs(): Promise<EventDefinition[]> {
  const directory = new URL('./', import.meta.url);
  const files = (await readdir(directory)).filter((name) => /\.event\.(ts|js)$/.test(name)).sort();
  return Promise.all(
    files.map(
      async (name) =>
        ((await import(new URL(name, directory).href)) as { default: EventDefinition }).default,
    ),
  );
}
