import type { EventAccount } from '../../../../shared/src/events.js';
export class AttendanceService {
  claimDay(account: EventAccount, namespace: string, now: Date, totalDays: number): number {
    const day = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Seoul',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(now);
    const days = account.attendance[namespace] ?? [];
    if (days.includes(day)) throw new Error('오늘 출석 보상을 이미 받았습니다.');
    if (days.length >= totalDays) throw new Error('모든 출석 보상을 받았습니다.');
    account.attendance[namespace] = [...days, day];
    return days.length;
  }
}
