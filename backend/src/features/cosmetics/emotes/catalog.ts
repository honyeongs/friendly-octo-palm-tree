import type { Cosmetic } from '../../../../../shared/src/events.js';
export const emotes: Cosmetic[] = [
  'christmas_2026',
  'summer_2027',
  'halloween_2026',
  'anniversary_2026',
].map((id) => ({
  id: `${id}_emote`,
  name: `${id.split('_')[0]} 축하 인사`,
  description: '함께 항해한 상인에게 보내는 인사',
  rarity: 'RARE',
  imageUrl: '/cosmetics/emote.svg',
  acquisitionType: 'EVENT',
  cosmeticType: 'EMOTE',
}));
