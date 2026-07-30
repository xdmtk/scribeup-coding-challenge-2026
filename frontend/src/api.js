const BASE = "http://localhost:8000";

export async function fetchUsers() {
  const r = await fetch(`${BASE}/users/`);
  if (!r.ok) throw new Error(`fetchUsers: ${r.status}`);
  return r.json();
}

export async function fetchTransactions(userId, signal) {
  const r = await fetch(`${BASE}/users/${userId}/transactions/`, { signal });
  if (!r.ok) throw new Error(`fetchTransactions: ${r.status}`);
  return r.json();
}

export async function fetchMerchantGroups(userId, signal) {
  const r = await fetch(`${BASE}/users/${userId}/merchant-groups/`, { signal });
  if (!r.ok) throw new Error(`fetchMerchantGroups: ${r.status}`);
  return r.json();
}

export async function fetchSubscriptions(userId, signal) {
  const r = await fetch(`${BASE}/users/${userId}/subscriptions/`, { signal });
  if (!r.ok) throw new Error(`fetchSubscriptions: ${r.status}`);
  return r.json();
}
