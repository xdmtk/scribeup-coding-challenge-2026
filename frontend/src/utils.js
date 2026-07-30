const currency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const shortDate = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });
const fullDate = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" });

export function formatCurrency(value) {
  const number = Number(value);
  return Number.isFinite(number) ? currency.format(number) : "—";
}

export function parseDateOnly(value) {
  if (!value) return null;
  const match = String(value).slice(0, 10).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return null;
  const [, year, month, day] = match;
  return new Date(Number(year), Number(month) - 1, Number(day));
}

export function formatDate(value, compact = false) {
  const date = parseDateOnly(value);
  return date ? (compact ? shortDate : fullDate).format(date) : "—";
}

export function monthlyEquivalent(subscription) {
  const amount = Number(subscription.typical_amount);
  if (!Number.isFinite(amount)) return null;
  const cadence = String(subscription.cadence || "").toLowerCase();
  const factors = { weekly: 52 / 12, biweekly: 26 / 12, monthly: 1, quarterly: 1 / 3, yearly: 1 / 12 };
  if (cadence in factors) return amount * factors[cadence];
  const interval = Number(subscription.typical_interval_days);
  return Number.isFinite(interval) && interval > 0 ? amount * 30.4375 / interval : null;
}

export function cadenceLabel(value, interval) {
  const cadence = String(value || "").toLowerCase();
  const labels = { weekly: "Weekly", biweekly: "Biweekly", monthly: "Monthly", quarterly: "Quarterly", yearly: "Yearly" };
  if (labels[cadence]) return labels[cadence];
  const days = Number(interval) || Number(cadence.match(/\d+/)?.[0]);
  return days > 0 ? `Every ${days} days` : cadence ? cadence.charAt(0).toUpperCase() + cadence.slice(1) : "Unknown";
}

export function earliestNextCharge(subscriptions) {
  return subscriptions.reduce((earliest, item) => {
    const date = parseDateOnly(item.next_predicted_charge_date);
    if (!date) return earliest;
    return !earliest || date < earliest.date ? { item, date } : earliest;
  }, null);
}

export function daysBetween(from, to) {
  if (!from || !to) return null;
  return Math.round((to.getTime() - from.getTime()) / 86400000);
}

export function titleize(value) {
  return String(value || "—").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
