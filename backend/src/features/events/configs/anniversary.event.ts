import { EventType } from '../EventTypes.js';
import { festival } from './festival.js';
// Sample launch celebration schedule; change this data when the actual launch date is decided.
export default festival(
  'anniversary_2026',
  '첫 항해 기념제 (샘플)',
  '2026-09-12T00:00:00+09:00',
  '2026-09-26T00:00:00+09:00',
  'ANNIVERSARY',
  'Anniversary Token',
  EventType.ANNIVERSARY,
);
