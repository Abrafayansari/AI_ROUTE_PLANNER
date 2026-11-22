/**
 * Utility to format time strings (e.g. "09:00", "13:30", "14:45", "00:00")
 * or minutes from midnight (e.g. 540 -> "09:00 AM", 810 -> "01:30 PM")
 * into consistent 12-hour AM/PM format.
 */

export function formatTime12Hour(time: string | number | null | undefined): string {
  if (time === null || time === undefined || time === '') {
    return '';
  }

  let totalMinutes: number;

  if (typeof time === 'number') {
    totalMinutes = Math.round(time);
  } else {
    const trimmed = String(time).trim();
    if (!trimmed) return '';

    // If it's already in 12-hour AM/PM format (e.g., "09:00 AM" or "1:30 pm")
    const ampmMatch = trimmed.match(/^(\d{1,2}):(\d{2})\s*([AaPp][Mm])$/);
    if (ampmMatch) {
      let h = parseInt(ampmMatch[1], 10);
      const m = ampmMatch[2];
      const p = ampmMatch[3].toUpperCase();
      if (h === 0) h = 12;
      return `${String(h).padStart(2, '0')}:${m} ${p}`;
    }

    // Try parsing HH:MM or HH:MM:SS
    const parts = trimmed.split(':');
    if (parts.length >= 2) {
      const h = parseInt(parts[0], 10);
      const m = parseInt(parts[1], 10);
      if (!isNaN(h) && !isNaN(m)) {
        totalMinutes = h * 60 + m;
      } else {
        return trimmed;
      }
    } else {
      const num = Number(trimmed);
      if (!isNaN(num)) {
        totalMinutes = Math.round(num);
      } else {
        return trimmed;
      }
    }
  }

  // Normalize totalMinutes to 0..1439
  totalMinutes = ((totalMinutes % 1440) + 1440) % 1440;

  const hours24 = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;

  const period = hours24 >= 12 ? 'PM' : 'AM';
  let hours12 = hours24 % 12;
  if (hours12 === 0) {
    hours12 = 12;
  }

  const formattedHours = String(hours12).padStart(2, '0');
  const formattedMinutes = String(minutes).padStart(2, '0');

  return `${formattedHours}:${formattedMinutes} ${period}`;
}
