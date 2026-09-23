const REQUEST_ID_PREFIX = 'CVT25X';
const RANDOM_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';

function pad(value: number): string {
  return String(value).padStart(2, '0');
}

function timestampStamp(date: Date): string {
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
    pad(date.getHours()),
    pad(date.getMinutes()),
    pad(date.getSeconds()),
  ].join('');
}

function randomSuffix(length = 6): string {
  let output = '';
  for (let i = 0; i < length; i += 1) {
    output += RANDOM_CHARS[Math.floor(Math.random() * RANDOM_CHARS.length)];
  }
  return output;
}

export function createRequestId(now: Date = new Date()): string {
  return `${REQUEST_ID_PREFIX}-${timestampStamp(now)}-${randomSuffix(6)}`;
}
