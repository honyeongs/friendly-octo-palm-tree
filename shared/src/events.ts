export enum EventType {
  SEASONAL = 'SEASONAL',
  ANNIVERSARY = 'ANNIVERSARY',
  COLLABORATION = 'COLLABORATION',
  SPECIAL = 'SPECIAL',
  WEEKEND = 'WEEKEND',
}
export type EventStatus = 'UPCOMING' | 'ACTIVE' | 'ENDED';
export type CosmeticType = 'DICE_SKIN' | 'PROFILE_FRAME' | 'EMOTE' | 'PLAYER_TOKEN';
export type AcquisitionMethod =
  'EVENT_SHOP' | 'EVENT_MISSION' | 'EVENT_ATTENDANCE' | 'EVENT_REWARD' | 'RANDOM_BOX';
export interface Cosmetic {
  id: string;
  name: string;
  description: string;
  rarity: 'COMMON' | 'RARE' | 'EPIC' | 'LEGENDARY';
  imageUrl: string;
  acquisitionType: 'DEFAULT' | 'SHOP' | 'ATTENDANCE' | 'MISSION' | 'EVENT' | 'ACHIEVEMENT';
  cosmeticType: CosmeticType;
}
export interface DiceSkin extends Cosmetic {
  cosmeticType: 'DICE_SKIN';
}
export interface Event {
  id: string;
  name: string;
  description: string;
  eventType: EventType;
  startAt: string;
  endAt: string;
  active: boolean;
  bannerImageUrl: string;
  theme: string;
  createdAt: string;
}
export interface EventCosmetic {
  id: string;
  eventId: string;
  cosmeticType: CosmeticType;
  cosmeticId: string;
  acquisitionMethod: AcquisitionMethod;
  availableFrom: string;
  availableUntil: string;
}
export interface EventCurrency {
  id: string;
  eventId: string;
  name: string;
  iconUrl: string;
}
export interface UserEventCurrency {
  userId: string;
  eventCurrencyId: string;
  amount: number;
}
export interface RewardSpec {
  rewardType: 'EVENT_CURRENCY' | 'COIN' | 'COSMETIC' | 'BOX';
  rewardId: string;
  rewardAmount: number;
}
export type MissionTarget = 'PLAY_GAME' | 'WIN_GAME' | 'BUY_CITY' | 'BUILD_LANDMARK';
export interface EventMission extends RewardSpec {
  id: string;
  eventId: string;
  title: string;
  description: string;
  targetType: MissionTarget;
  targetAmount: number;
}
export interface EventShopItem {
  id: string;
  eventId: string;
  itemType: CosmeticType;
  itemId: string;
  price: number;
  currencyId: string;
  purchaseLimit: number;
  availableFrom: string;
  availableUntil: string;
}
export interface EventDefinition extends Event {
  currency: EventCurrency;
  cosmetics: EventCosmetic[];
  missions: EventMission[];
  shop: EventShopItem[];
  attendance: RewardSpec[];
  rewards: Array<RewardSpec & { id: string; title: string }>;
}
export interface EventParticipation {
  userId: string;
  eventId: string;
  joinedAt: string;
  missionsCompleted: number;
  rewardsClaimed: number;
}
export interface RewardHistory {
  id: string;
  eventId: string;
  userId: string;
  source: string;
  reward: RewardSpec;
  grantedAt: string;
}
export interface EventAccount {
  userId: string;
  currencies: Record<string, number>;
  coins: number;
  boxes: Record<string, number>;
  inventory: Record<string, { cosmeticId: string; acquiredAt: string; source: string }>;
  equipped: Partial<Record<CosmeticType, string>>;
  purchases: Record<string, number>;
  missions: Record<string, { progress: number; claimed: boolean }>;
  attendance: Record<string, string[]>;
  claims: string[];
  processedFacts: string[];
  participation: Record<string, EventParticipation>;
  history: RewardHistory[];
}
export interface EventPage {
  definition: EventDefinition;
  status: EventStatus;
  remainingMs: number;
}
export interface EventDashboard {
  serverTime: string;
  events: EventPage[];
  cosmetics: Cosmetic[];
  account: EventAccount;
}
