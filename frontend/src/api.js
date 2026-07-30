const BASE = "http://localhost:8000";

export async function fetchUsers() {
  const r = await fetch(`${BASE}/users/`);
  if (!r.ok) throw new Error(`fetchUsers: ${r.status}`);
  return r.json();
}

export async function fetchTransactions(userId) {
  const r = await fetch(`${BASE}/users/${userId}/transactions/`);
  if (!r.ok) throw new Error(`fetchTransactions: ${r.status}`);
  return r.json();
}

export async function fetchMerchantGroups(userId) {
  const r = await fetch(`${BASE}/users/${userId}/merchant-groups/`);
  if (!r.ok) throw new Error(`fetchMerchantGroups: ${r.status}`);
  return r.json();
}

export async function fetchSubscriptions(userId) {
  const r = await fetch(`${BASE}/users/${userId}/subscriptions/`);
  if (!r.ok) throw new Error(`fetchSubscriptions: ${r.status}`);
  return r.json();
}
