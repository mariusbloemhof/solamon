export function fmt(value: number, digits = 1): string {
  return value.toLocaleString("en-ZA", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  });
}

export function nowTime(): string {
  return new Date().toLocaleTimeString("en-ZA", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
}
