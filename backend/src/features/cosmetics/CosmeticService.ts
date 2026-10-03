import { diceSkins } from './dice/catalog.js';
import { profileFrames } from './profileFrames/catalog.js';
import { emotes } from './emotes/catalog.js';
export class CosmeticService {
  list() {
    return structuredClone([...diceSkins, ...profileFrames, ...emotes]);
  }
  get(id: string) {
    const item = this.list().find((c) => c.id === id);
    if (!item) throw new Error('스킨을 찾을 수 없습니다.');
    return item;
  }
}
