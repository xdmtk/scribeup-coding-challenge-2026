import { useEffect, useRef, useState } from "react";

import {
  fetchMerchantGroups,
  fetchSubscriptions,
  fetchTransactions,
  fetchUsers,
} from "./api.js";
import {
  DashboardHeader,
  DetectionModal,
  RecentTransactions,
  SubscriptionsTable,
  SummaryCards,
} from "./components.jsx";
import "./styles.css";

export default function App() {
  const [userIds, setUserIds] = useState([]);
  const [selectedUser, setSelectedUser] = useState(null);

  const [transactions, setTransactions] = useState([]);
  const [transactionsLoading, setTransactionsLoading] = useState(false);
  const [transactionsError, setTransactionsError] = useState(null);

  const [subscriptions, setSubscriptions] = useState([]);
  const [subscriptionsLoading, setSubscriptionsLoading] = useState(false);
  const [subscriptionsError, setSubscriptionsError] = useState(null);

  const [modalOpen, setModalOpen] = useState(false);
  const [groups, setGroups] = useState(null);
  const [groupsLoading, setGroupsLoading] = useState(false);
  const [groupsError, setGroupsError] = useState(null);

  const diagnosticRequest = useRef(null);

  useEffect(() => {
    let active = true;

    fetchUsers()
      .then((data) => {
        if (!active) return;

        setUserIds(data.user_ids);

        if (data.user_ids.length > 0) {
          setSelectedUser(data.user_ids[0]);
        }
      })
      .catch((error) => {
        if (active) {
          setTransactionsError(error.message);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (selectedUser == null) {
      return undefined;
    }

    const controller = new AbortController();

    setTransactions([]);
    setTransactionsLoading(true);
    setTransactionsError(null);

    setSubscriptions([]);
    setSubscriptionsLoading(true);
    setSubscriptionsError(null);

    fetchTransactions(selectedUser, controller.signal)
      .then((data) => {
        setTransactions(data.transactions);
      })
      .catch((error) => {
        if (error.name !== "AbortError") {
          setTransactionsError(error.message);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setTransactionsLoading(false);
        }
      });

    fetchSubscriptions(selectedUser, controller.signal)
      .then((data) => {
        setSubscriptions(data.subscriptions);
      })
      .catch((error) => {
        if (error.name !== "AbortError") {
          setSubscriptionsError(error.message);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setSubscriptionsLoading(false);
        }
      });

    return () => {
      controller.abort();
    };
  }, [selectedUser]);

  useEffect(() => {
    if (!modalOpen) {
      return undefined;
    }

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        diagnosticRequest.current?.abort();
        setModalOpen(false);
        setGroupsLoading(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    document.body.classList.add("modal-open");

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      document.body.classList.remove("modal-open");
    };
  }, [modalOpen]);

  const inspect = () => {
    if (selectedUser == null) {
      return;
    }

    diagnosticRequest.current?.abort();

    const controller = new AbortController();
    diagnosticRequest.current = controller;

    setModalOpen(true);
    setGroups(null);
    setGroupsLoading(true);
    setGroupsError(null);

    fetchMerchantGroups(selectedUser, controller.signal)
      .then((data) => {
        setGroups(data);
      })
      .catch((error) => {
        if (error.name !== "AbortError") {
          setGroupsError(error.message);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setGroupsLoading(false);
        }
      });
  };

  const closeModal = () => {
    diagnosticRequest.current?.abort();
    diagnosticRequest.current = null;

    setModalOpen(false);
    setGroupsLoading(false);
  };

  const handleUserChange = (userId) => {
    closeModal();
    setSelectedUser(userId);
  };

  return (
    <main className="app-shell">
      <DashboardHeader
        userIds={userIds}
        selectedUser={selectedUser}
        onUserChange={handleUserChange}
        onInspect={inspect}
      />

      <SummaryCards
        subscriptions={subscriptions}
        transactions={transactions}
      />

      <SubscriptionsTable
        subscriptions={subscriptions}
        transactions={transactions}
        loading={subscriptionsLoading}
        error={subscriptionsError}
      />

      <RecentTransactions
        transactions={transactions}
        loading={transactionsLoading}
        error={transactionsError}
      />

      {modalOpen && (
        <DetectionModal
          groups={groups}
          loading={groupsLoading}
          error={groupsError}
          onClose={closeModal}
        />
      )}
    </main>
  );
}