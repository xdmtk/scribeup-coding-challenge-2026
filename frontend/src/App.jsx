import { useEffect, useState } from "react";
import { fetchMerchantGroups, fetchTransactions, fetchUsers } from "./api.js";

export default function App() {
  const [userIds, setUserIds] = useState([]);
  const [selectedUser, setSelectedUser] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [groupsOpen, setGroupsOpen] = useState(false);
  const [merchantGroups, setMerchantGroups] = useState(null);
  const [groupsLoading, setGroupsLoading] = useState(false);
  const [groupsError, setGroupsError] = useState(null);

  useEffect(() => {
    fetchUsers()
      .then((data) => {
        setUserIds(data.user_ids);
        if (data.user_ids.length) setSelectedUser(data.user_ids[0]);
      })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (selectedUser == null) return;
    setLoading(true);
    setError(null);
    fetchTransactions(selectedUser)
      .then((data) => setTransactions(data.transactions))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [selectedUser]);

  useEffect(() => {
    if (!groupsOpen) return undefined;
    const closeOnEscape = (event) => {
      if (event.key === "Escape") setGroupsOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [groupsOpen]);

  const openMerchantGroups = () => {
    if (selectedUser == null) return;
    setGroupsOpen(true);
    setGroupsLoading(true);
    setGroupsError(null);
    setMerchantGroups(null);
    fetchMerchantGroups(selectedUser)
      .then(setMerchantGroups)
      .catch((e) => setGroupsError(e.message))
      .finally(() => setGroupsLoading(false));
  };

  return (
    <div style={styles.page}>
      <h1 style={styles.h1}>ScribeUp Take-Home</h1>

      <div style={styles.controls}>
        <label>
          User:&nbsp;
          <select
            value={selectedUser ?? ""}
            onChange={(e) => setSelectedUser(Number(e.target.value))}
            style={styles.select}
          >
            {userIds.map((id) => (
              <option key={id} value={id}>
                User {id}
              </option>
            ))}
          </select>
        </label>
        <button style={styles.button} disabled={selectedUser == null} onClick={openMerchantGroups}>
          Current Subscriptions
        </button>
      </div>

      {/* TODO (candidate): render detected subscriptions for the selected user here. */}

      <h2 style={styles.h2}>Transactions</h2>
      {loading && <div>Loading…</div>}
      {error && <div style={styles.error}>Error: {error}</div>}
      {!loading && !error && (
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Date</th>
              <th style={styles.th}>Merchant</th>
              <th style={styles.th}>Amount</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((t) => (
              <tr key={t.id}>
                <td style={styles.td}>{t.charged_at.slice(0, 10)}</td>
                <td style={styles.td}>{t.merchant_name}</td>
                <td style={styles.td}>${t.amount}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {groupsOpen && (
        <MerchantGroupsModal
          groups={merchantGroups}
          loading={groupsLoading}
          error={groupsError}
          onClose={() => setGroupsOpen(false)}
        />
      )}
    </div>
  );
}

function MerchantGroupsModal({ groups, loading, error, onClose }) {
  const empty =
    groups && !groups.repeated_merchants.length && !groups.likely_one_off_merchants.length;
  return (
    <div style={styles.backdrop} role="presentation" onMouseDown={onClose}>
      <section
        style={styles.modal}
        role="dialog"
        aria-modal="true"
        aria-labelledby="merchant-groups-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div style={styles.modalHeader}>
          <h2 id="merchant-groups-title" style={styles.modalTitle}>Merchant Groups</h2>
          <button style={styles.closeButton} onClick={onClose} aria-label="Close">×</button>
        </div>
        <p style={styles.note}>
          Repeated merchants are candidates for subscription detection. They are not yet confirmed subscriptions.
        </p>
        <div style={styles.modalContent}>
          {loading && <div>Loading merchant groups…</div>}
          {error && <div style={styles.error}>Error: {error}</div>}
          {empty && <div>No merchant groups found for this user.</div>}
          {groups && !empty && (
            <>
              <MerchantSection title="Repeated merchants" groups={groups.repeated_merchants} />
              <MerchantSection title="Likely one-off merchants" groups={groups.likely_one_off_merchants} />
            </>
          )}
        </div>
      </section>
    </div>
  );
}

function MerchantSection({ title, groups }) {
  return (
    <section>
      <h3 style={styles.sectionTitle}>{title}</h3>
      {!groups.length && <p style={styles.muted}>None</p>}
      {groups.map((group) => (
        <details key={group.normalized_merchant} style={styles.group}>
          <summary style={styles.summary}>
            <strong>{group.display_merchant}</strong> — {group.transaction_count} transaction{group.transaction_count === 1 ? "" : "s"}
          </summary>
          {group.merchant_variants.length > 1 && (
            <p style={styles.variants}>Variants: {group.merchant_variants.join(", ")}</p>
          )}
          <div style={styles.transactionList}>
            {group.transactions.map((transaction) => (
              <div key={transaction.id} style={styles.groupTransaction}>
                <span>{transaction.charged_at.slice(0, 10)}</span>
                <span>{transaction.merchant_name}</span>
                <span style={styles.amount}>${transaction.amount}</span>
              </div>
            ))}
          </div>
        </details>
      ))}
    </section>
  );
}

const styles = {
  page: { fontFamily: "system-ui, sans-serif", maxWidth: 720, margin: "40px auto", padding: 16 },
  h1: { fontSize: 24, marginBottom: 16 },
  h2: { fontSize: 18, marginTop: 24, marginBottom: 8 },
  controls: { display: "flex", alignItems: "center", flexWrap: "wrap", gap: 10, marginBottom: 16 },
  select: { padding: 6, fontSize: 14 },
  button: { padding: "7px 10px", fontSize: 14, cursor: "pointer" },
  table: { width: "100%", borderCollapse: "collapse", fontSize: 14 },
  th: { textAlign: "left", borderBottom: "1px solid #ddd", padding: 8 },
  td: { borderBottom: "1px solid #f0f0f0", padding: 8 },
  error: { color: "crimson" },
  backdrop: { position: "fixed", inset: 0, background: "rgba(0, 0, 0, 0.45)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16, zIndex: 10 },
  modal: { background: "white", borderRadius: 6, width: "min(760px, 100%)", maxHeight: "85vh", display: "flex", flexDirection: "column", boxShadow: "0 8px 30px rgba(0, 0, 0, 0.25)" },
  modalHeader: { display: "flex", justifyContent: "space-between", alignItems: "center", padding: "16px 18px 0" },
  modalTitle: { fontSize: 20, margin: 0 },
  closeButton: { border: 0, background: "transparent", fontSize: 28, lineHeight: 1, cursor: "pointer" },
  note: { margin: "10px 18px", color: "#555", fontSize: 14 },
  modalContent: { overflowY: "auto", padding: "0 18px 18px" },
  sectionTitle: { fontSize: 16, margin: "18px 0 8px" },
  muted: { color: "#666", fontSize: 14 },
  group: { borderTop: "1px solid #ddd", padding: "10px 2px" },
  summary: { cursor: "pointer", fontSize: 14 },
  variants: { color: "#555", fontSize: 13, margin: "8px 0" },
  transactionList: { marginTop: 8 },
  groupTransaction: { display: "grid", gridTemplateColumns: "minmax(90px, 0.8fr) minmax(120px, 2fr) minmax(70px, 0.6fr)", gap: 8, padding: "6px 4px", borderTop: "1px solid #f0f0f0", fontSize: 13 },
  amount: { textAlign: "right" },
};
