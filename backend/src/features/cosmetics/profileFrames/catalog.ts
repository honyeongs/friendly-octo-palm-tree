import type { Cosmetic } from '../../../../../shared/src/events.js';
export const profileFrames: Cosmetic[] = [
  'christmas_2026',
  'summer_2027',
  'halloween_2026',
  'anniversary_2026',
].map((id) => ({
  id: `${id}_frame`,
  name: `${id.split('_')[0]} 기념 프레임`,
  description: '축제의 기억을 담은 테두리',
  rarity: 'EPIC',
  imageUrl: '/cosmetics/frame.svg',
  acquisitionType: 'EVENT',
  cosmeticType: 'PROFILE_FRAME',
}));
