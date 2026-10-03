import type { Tile } from '../../../shared/src/index.js';

const names = [
  '새벽항',
  '구름정원',
  '유리숲',
  '별우물',
  '물결마루',
  '노을공방',
  '달빛언덕',
  '반딧골',
  '바람서가',
  '청옥부두',
  '비취들',
  '해무시장',
  '은솔마을',
  '빛고래섬',
  '호박광장',
  '이슬고원',
  '오로라뜰',
  '남빛골목',
  '하늘등대',
  '여울정원',
  '수정계곡',
  '별가루장',
  '보랏빛항',
  '금빛둥지',
];
export function createBoard(): Tile[] {
  let city = 0;
  return Array.from({ length: 32 }, (_, index) => {
    const tile: Tile = {
      id: `tile-${index}`,
      index,
      type: 'CITY',
      name: '',
      purchasePrice: 0,
      baseToll: 0,
      ownerId: null,
      buildingLevel: 0,
      specialEffect: null,
      groupId: null,
    };
    if (index === 0) return { ...tile, type: 'START', name: '별길 출항' };
    if ([4, 12, 20, 28].includes(index))
      return { ...tile, type: 'EVENT', name: '바람 소식', specialEffect: { kind: 'EVENT' } };
    if (index === 8)
      return {
        ...tile,
        type: 'REST',
        name: '안개 쉼터',
        specialEffect: { kind: 'REST', turns: 1 },
      };
    if (index === 16)
      return {
        ...tile,
        type: 'TRAVEL',
        name: '순풍 항로',
        specialEffect: { kind: 'TRAVEL', destination: 24 },
      };
    if (index === 24)
      return {
        ...tile,
        type: 'TRAVEL',
        name: '귀항 항로',
        specialEffect: { kind: 'TRAVEL', destination: 0 },
      };
    const tier = Math.floor(index / 8);
    const name = names[city++]!;
    return {
      ...tile,
      name,
      purchasePrice: 160 + tier * 60 + (index % 4) * 20,
      baseToll: 35 + tier * 15 + (index % 3) * 5,
      groupId: `district-${tier}`,
    };
  });
}
