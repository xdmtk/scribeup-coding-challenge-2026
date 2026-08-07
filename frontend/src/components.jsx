import { useMemo, useState } from "react";
import { cadenceLabel, daysBetween, earliestNextCharge, formatCurrency, formatDate, monthlyEquivalent, parseDateOnly, titleize } from "./utils.js";

const sourceLabels = {
  heuristic: "Deterministic",
  llm_review: "Semantic review",
  heuristic_fallback: "Needs review"
};

export function StatusBadge({ value, children }) {
  const normalized = String(value || "neutral").replaceAll("_", "-");
  return <span className={`badge badge--${normalized}`}>
    {children ?? titleize(value)}
  </span>;
}

export function DashboardHeader({ userIds, selectedUser, onUserChange, onInspect }) {
  return <header className="dashboard-header">
    <div>
      <p className="eyebrow">ScribeUp Take-Home</p>
      <h1>Subscription Intelligence</h1>
      <p className="subtitle">Recurring charges detected from transaction history using deterministic analysis and selective semantic review.</p>
    </div>
    <div className="header-controls">
      <label className="field">
        <span>User</span>
        <select
          value={selectedUser ?? ""}
          onChange={(event) => onUserChange(Number(event.target.value))}
        >
          {userIds.map((id) => <option key={id} value={id}>User {id}</option>)}
        </select>
      </label>
      <button
        className="button button--secondary"
        disabled={selectedUser == null}
        onClick={onInspect}
      >
        Inspect detection
      </button>
    </div>
  </header>;
}

export function SummaryCards({ subscriptions, transactions }) {
  const monthly = subscriptions.map(monthlyEquivalent).filter((value) => value != null).reduce((sum, value) => sum + value, 0);
  const next = earliestNextCharge(subscriptions);
  return <section className="summary-grid" aria-label="Subscription summary">
    <Summary value={subscriptions.length} label="Detected subscriptions" />
    <Summary value={formatCurrency(monthly)} label="Estimated monthly" />
    <Summary value={subscriptions.filter((item) => item.cadence === "yearly").length} label="Annual plans" />
    <Summary value={next?.item.merchant ?? "No charge scheduled"} label={next ? formatDate(next.item.next_predicted_charge_date, true) : "Next expected charge"} compact />
  </section>;
}

function Summary({ value, label, compact }) {
  return <article className="summary-card">
    <span className={`summary-value${compact ? " summary-value--compact" : ""}`}>
      {value}
    </span>
    <span className="summary-label">{label}</span>
  </article>;
}

function SubscriptionContent({ item, referenceDate }) {
  const monthly = monthlyEquivalent(item);
  const next = parseDateOnly(item.next_predicted_charge_date);
  const days = daysBetween(referenceDate, next);
  return <>
    <div className="merchant"><span className="merchant-initial" aria-hidden="true">{item.merchant?.trim()?.[0]?.toUpperCase() || "?"}</span>
      <span><strong>{item.merchant}</strong><small>{sourceLabels[item.assessment_source] || titleize(item.assessment_source)}</small></span></div>
    <div><StatusBadge value={item.assessment_source}>{sourceLabels[item.assessment_source] || titleize(item.assessment_source)}</StatusBadge></div>
    <div><span className="cadence-pill">{cadenceLabel(item.cadence, item.typical_interval_days)}</span></div>
    <div className="money">{formatCurrency(item.typical_amount)}</div>
    <div className="money">{monthly == null ? "—" : `${formatCurrency(monthly)}/mo`}</div>
    <div className="date-cell"><span>{formatDate(item.next_predicted_charge_date)}</span>{days >= 0 && <small>{days === 0 ? "expected today" : `in ${days} days`}</small>}</div>
  </>;
}

export function SubscriptionsTable({ subscriptions, loading, error, transactions }) {
  const referenceDate = transactions.reduce((latest, txn) => { const date = parseDateOnly(txn.charged_at); return date && (!latest || date > latest) ? date : latest; }, null) || new Date();
  return <section className="panel" aria-labelledby="subscriptions-heading"><div className="panel-heading"><div><p className="section-kicker">Portfolio</p><h2 id="subscriptions-heading">Detected subscriptions</h2></div><span className="count">{subscriptions.length}</span></div>
    {loading && <LoadingState label="Loading subscriptions" />}
    {error && <ErrorState title="Subscriptions unavailable" message={error} />}
    {!loading && !error && !subscriptions.length && <EmptyState title="No finalized subscriptions were detected for this user." message="Recurring activity may still appear in detection analysis as possible or unlikely." />}
    {!loading && !error && subscriptions.length > 0 && <>
      <div className="subscription-table"><div className="table-row table-head"><span>Merchant</span><span>Detection</span><span>Cadence</span><span>Typical charge</span><span>Monthly equivalent</span><span>Next charge</span></div>
        {subscriptions.map((item) => <div className="table-row" key={item.merchant}><SubscriptionContent item={item} referenceDate={referenceDate} /></div>)}</div>
      <div className="subscription-mobile">{subscriptions.map((item) => <article className="subscription-card" key={item.merchant}><SubscriptionContent item={item} referenceDate={referenceDate} /></article>)}</div>
    </>}
  </section>;
}

export function RecentTransactions({ transactions, loading, error }) {
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState(false);
  const filtered = useMemo(() => transactions.filter((item) => item.merchant_name.toLowerCase().includes(query.trim().toLowerCase())), [query, transactions]);
  const shown = expanded ? filtered : filtered.slice(0, 10);
  return <section className="panel" aria-labelledby="transactions-heading"><div className="panel-heading panel-heading--tools"><div><p className="section-kicker">Activity</p><h2 id="transactions-heading">Recent transactions</h2></div>
    <label className="search"><span className="sr-only">Search transactions</span><input type="search" placeholder="Search transactions" value={query} onChange={(event) => setQuery(event.target.value)} /></label></div>
    {loading && <LoadingState label="Loading transactions" />}{error && <ErrorState title="Transactions unavailable" message={error} />}
    {!loading && !error && !transactions.length && <EmptyState title="No transactions found for this user." message="Transactions will appear here when they are available." />}
    {!loading && !error && transactions.length > 0 && <>{!shown.length ? <EmptyState title="No matching transactions." message="Try a different merchant search." /> : <div className="transactions-table"><div className="transaction-row table-head"><span>Date</span><span>Merchant</span><span>Amount</span></div>
      {shown.map((item) => <div className="transaction-row" key={item.id}><span>{formatDate(item.charged_at)}</span><strong>{item.merchant_name}</strong><span className="money">{formatCurrency(item.amount)}</span></div>)}</div>}
      {filtered.length > 10 && <div className="panel-footer"><button className="button button--text" onClick={() => setExpanded((value) => !value)}>{expanded ? "Show fewer" : "View all transactions"}</button></div>}</>}
  </section>;
}

export function LoadingState({ label }) {
  return <div className="state state--loading" role="status">
    <span className="spinner" />
    {label}…
  </div>;
}

export function ErrorState({ title, message }) {
  return <div className="state state--error" role="alert">
    <strong>{title}</strong>
    <span>{message}</span>
  </div>;
}

export function EmptyState({ title, message }) {
  return <div className="state">
    <span className="empty-mark" aria-hidden="true">—</span>
    <strong>{title}</strong>
    <span>{message}</span>
  </div>;
}

export function DetectionModal({ groups, loading, error, onClose }) {
  // The modal exposes diagnostic heuristic results alongside, but separately
  // from, any finalized subscription assessment stored for the dashboard.
  const [tab, setTab] = useState("groups");
  const [filter, setFilter] = useState("likely");
  const analysis = groups?.subscription_analysis;
  const categories = {
    likely: analysis?.likely_subscriptions || [],
    possible: analysis?.possible_subscriptions || [],
    unlikely: analysis?.unlikely_subscriptions || []
  };
  const groupCount = (groups?.repeated_merchants?.length || 0) + (groups?.likely_one_off_merchants?.length || 0);
  const resultCount = Object.values(categories).reduce((sum, items) => sum + items.length, 0);
  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="detection-title" onMouseDown={(event) => event.stopPropagation()}>
    <header className="modal-header"><div><h2 id="detection-title">Detection analysis</h2><p>Inspect merchant grouping, deterministic evidence, and persisted final decisions.</p></div><button className="close-button" onClick={onClose} aria-label="Close detection analysis">×</button></header>
    <div className="tabs" role="tablist" aria-label="Detection analysis views"><Tab selected={tab === "groups"} onClick={() => setTab("groups")}>Merchant groups <span>{groupCount}</span></Tab><Tab selected={tab === "results"} onClick={() => setTab("results")}>Detection results <span>{resultCount}</span></Tab></div>
    <p className="explanation">{tab === "groups" ? "Repeated merchants are candidates for analysis, not confirmed subscriptions." : "The heuristic result remains deterministic. Semantic review only resolves ambiguous “possible” cases, and its final result is stored separately."}</p>
    <div className="modal-content">{loading && <LoadingState label="Loading detection analysis" />}{error && <ErrorState title="Detection analysis unavailable" message={error} />}
      {!loading && !error && groups && tab === "groups" && <><AnalysisSection title="Repeated merchants" items={groups.repeated_merchants} simple /><AnalysisSection title="Likely one-off merchants" items={groups.likely_one_off_merchants} simple /></>}
      {!loading && !error && groups && tab === "results" && <><div className="filters" aria-label="Detection result filters">{Object.entries(categories).map(([name, items]) => <button key={name} className={filter === name ? "filter active" : "filter"} aria-pressed={filter === name} onClick={() => setFilter(name)}>{titleize(name)} <span>{items.length}</span></button>)}</div><AnalysisSection title={`${titleize(filter)} results`} items={categories[filter]} /></>}
    </div></section></div>;
}

function Tab({ selected, onClick, children }) { return <button role="tab" aria-selected={selected} className={selected ? "tab active" : "tab"} onClick={onClick}>{children}</button>; }

function AnalysisSection({ title, items = [], simple }) {
  return <section className="analysis-section"><h3>{title}</h3>{!items.length && <p className="muted">No results in this category.</p>}{items.map((group) => simple ? <SimpleGroup key={group.normalized_merchant} group={group} /> : <AnalysisCard key={group.normalized_merchant} group={group} />)}</section>;
}
function SimpleGroup({ group }) { return <details className="analysis-card"><summary><span><strong>{group.display_merchant}</strong><small>{group.transaction_count} transaction{group.transaction_count === 1 ? "" : "s"}</small></span><StatusBadge value="neutral">Merchant group</StatusBadge></summary><TransactionList items={group.transactions} /></details>; }
function AnalysisCard({ group }) {
  const cadence = group.detected_cadence;
  const amount = group.amount_analysis;
  const final = group.final_assessment;
  return <details className="analysis-card"><summary><span><strong>{group.display_merchant}</strong><small>{cadenceLabel(cadence.label, cadence.typical_interval_days)} · {group.transaction_count} charges · {formatCurrency(amount.typical_amount)} typical</small></span><StatusBadge value={group.classification}>{titleize(group.classification)}</StatusBadge></summary>
    <div className="assessment-grid"><Metric label="Heuristic result"><StatusBadge value={group.classification} /></Metric><Metric label="Final result">{final ? <StatusBadge value={final.final_classification}>{titleize(final.final_classification)}</StatusBadge> : "Not stored"}</Metric><Metric label="Assessment source">{final ? sourceLabels[final.assessment_source] || titleize(final.assessment_source) : "Deterministic only"}</Metric><Metric label="LLM status">{final ? titleize(final.llm_review_status) : "Not requested"}</Metric><Metric label="Confidence">{Math.round(group.confidence_score * 100)}%</Metric><Metric label="Cadence">{cadenceLabel(cadence.label, cadence.typical_interval_days)}</Metric></div>
    <div className="evidence-grid"><Evidence title="Timing" rows={[['Observed intervals', cadence.intervals_days.length ? `${cadence.intervals_days.join(", ")} days` : "Not enough history"], ['Timing consistency', `${Math.round(cadence.consistency_score * 100)}%`], ['Intervals explained', `${Math.round((cadence.explained_ratio || 0) * 100)}%`]]} /><Evidence title="Amounts" rows={[['Typical amount', formatCurrency(amount.typical_amount)], ['Amount range', `${formatCurrency(amount.min_amount)}–${formatCurrency(amount.max_amount)}`], ['Within 5%', `${Math.round(amount.within_five_percent_ratio * 100)}%`]]} /><Evidence title="History" rows={[['Transaction count', group.transaction_count], ['Evidence strength', `${Math.round(group.evidence_strength_score * 100)}%`], ['Pattern quality', `${Math.round(group.pattern_quality_score * 100)}%`]]} /><Evidence title="Activity" rows={[['Status', group.activity.apparently_active == null ? "Unavailable" : group.activity.apparently_active ? "Apparently active" : "Apparently inactive"], ['Days since last charge', group.activity.days_since_last_charge]]} /></div>
    <section className="evidence-list"><h4>Evidence</h4><ul>{group.evidence.map((item, index) => <li key={`${item.label}-${index}`} className={item.type}>{item.type === "positive" ? "+" : "−"} {item.label}</li>)}</ul></section><section><h4>Transactions</h4><TransactionList items={group.transactions} /></section>
  </details>;
}
function Metric({ label, children }) { return <div><span>{label}</span><strong>{children}</strong></div>; }
function Evidence({ title, rows }) { return <section><h4>{title}</h4>{rows.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value ?? "—"}</strong></div>)}</section>; }
function TransactionList({ items }) { return <div className="diagnostic-transactions">{items.map((item) => <div key={item.id}><span>{formatDate(item.charged_at)}</span><strong>{item.merchant_name}</strong><span>{formatCurrency(item.amount)}</span></div>)}</div>; }
