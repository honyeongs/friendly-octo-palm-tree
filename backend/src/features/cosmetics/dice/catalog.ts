import type { DiceSkin } from '../../../../../shared/src/events.js';
export const diceSkins: DiceSkin[] = [
  {
    id: 'default_dice',
    name: '별길 주사위',
    description: '모든 상인의 첫 주사위',
    rarity: 'COMMON',
    imageUrl: '/cosmetics/dice.svg',
    acquisitionType: 'DEFAULT',
    cosmeticType: 'DICE_SKIN',
  },
  ...(['christmas_2026', 'summer_2027', 'halloween_2026', 'anniversary_2026'] as const).map(
    (id, i): DiceSkin => ({
      id: `${id}_dice`,
      name: ['눈꽃 주사위', '바다 주사위', '호박빛 주사위', '첫 항해 주사위'][i]!,
      description: '기간 한정 교역 축제 기념 주사위',
      rarity: 'LEGENDARY',
      imageUrl: '/cosmetics/dice.svg',
      acquisitionType: 'EVENT',
      cosmeticType: 'DICE_SKIN',
    }),
  ),
];
