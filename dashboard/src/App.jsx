import React, { useState, useEffect, useRef } from 'react';
import {
  LayoutDashboard,
  CheckCircle2,
  History,
  Users,
  Bell,
  RefreshCw,
  Zap,
  Package,
  Briefcase,
  FolderKanban,
  Menu,
  ShoppingCart,
  Truck,
  UserCircle2,
  Receipt,
  IndianRupee,
  LayoutGrid,
  Bike,
  MessageSquare,
  Mic
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import Sidebar from './components/Sidebar';
import HomeTab from './components/HomeTab';
import ApprovalsTab from './components/ApprovalsTab';
import WhatHappenedTab from './components/WhatHappenedTab';
import AgentsTab from './components/AgentsTab';
import InventoryTab from './components/InventoryTab';
import CartTab from './components/CartTab';
import PlansTab from './components/PlansTab';
import WorkspaceTab from './components/WorkspaceTab';
import SuppliersTab from './components/SuppliersTab';
import AlertsPanel from './components/AlertsPanel';
import CustomersTab from './components/CustomersTab';
import OrdersTab from './components/OrdersTab';
import FinancialsTab from './components/FinancialsTab';
import ShelfTrackerTab from './components/ShelfTrackerTab';
import DeliveryQueueTab from './components/DeliveryQueueTab';
import CustomerAssistantTab from './components/CustomerAssistantTab';
import StaffTab from './components/StaffTab';
import PaymentsTab from './components/PaymentsTab';
import LoyaltyTab from './components/LoyaltyTab';
import BarcodeScannerTab from './components/BarcodeScannerTab';
import VoiceAssistantTab from './components/VoiceAssistantTab';
import LoginForm from './components/LoginForm';
import useOfflineSync from './useOfflineSync';

const getStoredToken = () => {
  try {
    return localStorage.getItem('retailos_token') || localStorage.getItem('token') || '';
  } catch {
    return '';
  }
};

const authHeaders = () => {
  const token = getStoredToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
};

const toArray = (value) => {
  if (Array.isArray(value)) return value;
  if (Array.isArray(value?.logs)) return value.logs;
  if (Array.isArray(value?.items)) return value.items;
  if (Array.isArray(value?.results)) return value.results;
  return [];
};

export default function App() {
  const [refreshTick, setRefreshTick] = useState(0);
  const [isKioskMode] = useState(() => new URLSearchParams(window.location.search).get('mode') === 'kiosk');
  const [activeTab, setActiveTab] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('mode') === 'kiosk') return 'assistant';
    return params.get('tab') || 'home';
  });
  const [logs, setLogs] = useState([]);
  const [approvals, setApprovals] = useState([]);
  const [agents, setAgents] = useState([]);
  const [stats, setStats] = useState({
    revenue: 0,
    approvalsOpen: 0,
    udhaarOutstanding: 0,
    payablesDue: 0,
  });
  const [plans] = useState([
    {
      id: 'ui-refresh',
      title: 'UI Experience Upgrade',
      owner: 'Product + Frontend',
      status: 'in_progress',
      progress: 68,
      summary: 'Polish the dashboard into a clearer, faster workspace with better structure and stronger decision surfaces.',
      focus: 'Navigation, homepage framing, approval visibility, and cleaner user-facing language.',
      nextAction: 'Finalize the new dashboard flow and connect future user-specific widgets to live data.',
      milestones: [
        { label: 'Navigation cleanup', done: true },
        { label: 'Add plans overview', done: true },
        { label: 'Surface workspace context', done: false },
        { label: 'Refine mobile layout', done: false },
      ],
    },
    {
      id: 'user-workspace',
      title: 'Custom User Work Setup',
      owner: 'Ops + Personalization',
      status: 'planned',
      progress: 42,
      summary: 'Shape the product around the user: role, routines, priorities, communication style, and preferred workflows.',
      focus: 'Morning checklist, approval style, business goals, notification preferences, and store context.',
      nextAction: 'Move these preferences from UI scaffolding into persistent backend settings and onboarding.',
      milestones: [
        { label: 'Map user profile fields', done: true },
        { label: 'Design workspace setup UI', done: true },
        { label: 'Persist preferences in API', done: false },
        { label: 'Enable editable routines', done: false },
      ],
    },
  ]);
  const [workspaceProfile] = useState({
    name: 'Soham',
    role: 'Store Owner',
    workStyle: 'Hands-on in the morning, approval-driven in the afternoon, summary-first at night.',
    location: 'Primary retail floor',
    goals: [
      'Reduce time spent chasing suppliers',
      'Keep approvals short and easy to review',
      'See the next important action without digging',
    ],
    routines: [
      { label: 'Morning opening check', time: '08:30', detail: 'Review low-stock items and overnight alerts.' },
      { label: 'Midday approval sweep', time: '13:00', detail: 'Approve urgent supplier and pricing decisions.' },
      { label: 'Evening summary', time: '20:30', detail: 'Get a short wrap-up of store actions and outcomes.' },
    ],
    preferences: [
      { label: 'Approval style', value: 'Quick summary + best option first' },
      { label: 'Notifications', value: 'Urgent only during business hours' },
      { label: 'Decision mode', value: 'Manual approval for supplier commits' },
      { label: 'Focus area', value: 'Inventory health and supplier savings' },
    ],
  });
  const [showAlerts, setShowAlerts] = useState(false);
  const [alertCount, setAlertCount] = useState(0);
  const [isConnected, setIsConnected] = useState(false);
  const [authRequired, setAuthRequired] = useState(false);
  const ws = useRef(null);
  const token = getStoredToken();

  // Offline-first sync engine
  const {
    isOnline,
    isSyncing,
    pendingCount,
    queueOperation,
    forceSync,
  } = useOfflineSync({
    authToken: token,
    onPulledChanges: () => {
      setRefreshTick((prev) => prev + 1);
    },
  });

  // Expose sync utilities to child components via window
  useEffect(() => {
    window.retailosSync = { queueOperation, forceSync, isOnline };
    return () => { delete window.retailosSync; };
  }, [queueOperation, forceSync, isOnline]);
  const navItems = [
    { id: 'home', label: 'Overview', icon: LayoutDashboard },
    { id: 'customers', label: 'Customers', icon: UserCircle2 },
    { id: 'orders', label: 'Orders', icon: Receipt },
    { id: 'financials', label: 'Financials', icon: IndianRupee },
    { id: 'assistant', label: 'Customer Bot', icon: MessageSquare },
    { id: 'inventory', label: 'Inventory', icon: Package },
    { id: 'cart', label: 'Cart', icon: ShoppingCart },
    { id: 'shelves', label: 'Shelves', icon: LayoutGrid },
    { id: 'delivery', label: 'Delivery', icon: Bike },
    { id: 'suppliers', label: 'Suppliers', icon: Truck },
    { id: 'voice', label: 'Voice Assistant', icon: Mic },
    { id: 'approvals', label: 'Approvals', icon: CheckCircle2, badge: approvals.length },
    { id: 'history', label: 'Activity', icon: History },
    { id: 'agents', label: 'Agents', icon: Users }
  ];

  useEffect(() => {
    try {
      const retailToken = localStorage.getItem('retailos_token');
      const legacyToken = localStorage.getItem('token');
      if (retailToken && !legacyToken) {
        localStorage.setItem('token', retailToken);
      }
    } catch {
      // ignore storage failures
    }

    fetchData();
    connectWebSocket();
    const interval = setInterval(fetchData, 30000);
    const handleDataChanged = () => {
      setRefreshTick((prev) => prev + 1);
      fetchData();
    };
    const handleNavigate = (event) => {
      const nextTab = event.detail?.tab;
      if (nextTab) setActiveTab(nextTab);
    };
    window.addEventListener('retailos:data-changed', handleDataChanged);
    window.addEventListener('retailos:navigate', handleNavigate);
    return () => {
      clearInterval(interval);
      window.removeEventListener('retailos:data-changed', handleDataChanged);
      window.removeEventListener('retailos:navigate', handleNavigate);
      if (ws.current) ws.current.close();
    };
  }, []);

  const fetchData = async () => {
    try {
      const [statusRes, approvalsRes, logsRes] = await Promise.all([
        fetch('/api/status', { headers: authHeaders() }),
        fetch('/api/approvals', { headers: authHeaders() }),
        fetch('/api/audit?limit=100', { headers: authHeaders() })
      ]);

      if ([statusRes, approvalsRes, logsRes].some((res) => res.status === 401)) {
        setAuthRequired(true);
        setAgents([]);
        setApprovals([]);
        setLogs([]);
        setStats({
          revenue: 0,
          approvalsOpen: 0,
          udhaarOutstanding: 0,
          payablesDue: 0,
        });
        setAlertCount(0);
        return;
      }

      const statusData = await statusRes.json();
      const approvalsData = await approvalsRes.json();
      const logsData = await logsRes.json();

      setAuthRequired(false);
      setAgents(toArray(statusData?.skills ?? statusData));
      setApprovals(toArray(approvalsData));
      setLogs(toArray(logsData));

      try {
        const [ordersRes, dailySummaryRes, vendorSummaryRes, udhaarRes] = await Promise.all([
          fetch('/api/orders', { headers: authHeaders() }),
          fetch('/api/daily-summary', { headers: authHeaders() }),
          fetch('/api/vendor-payments', { headers: authHeaders() }),
          fetch('/api/udhaar', { headers: authHeaders() }),
        ]);
        const [ordersData, dailySummaryData, vendorSummaryData, udhaarData] = await Promise.all([
          ordersRes.json(),
          dailySummaryRes.json(),
          vendorSummaryRes.json(),
          udhaarRes.json(),
        ]);

        setStats({
          revenue: dailySummaryData?.metrics?.revenue ?? ordersData?.customer_orders?.reduce((sum, order) => sum + (order.total_amount || 0), 0) ?? 0,
          approvalsOpen: approvalsData?.length || 0,
          udhaarOutstanding: dailySummaryData?.metrics?.udhaar_outstanding ?? udhaarData?.reduce((sum, ledger) => sum + (ledger.balance || 0), 0) ?? 0,
          payablesDue: vendorSummaryData?.total_unpaid ?? 0,
        });
      } catch {
        // ignore summary card failures so the rest of the dashboard still loads
      }

      try {
        const alertsRes = await fetch('/api/alerts?limit=20', { headers: authHeaders() });
        if (alertsRes.status === 401) {
          setAlertCount(0);
          return;
        }
        const alertsData = await alertsRes.json();
        const readAlerts = JSON.parse(localStorage.getItem('read_alerts') || '[]');
        const unread = toArray(alertsData).filter((a) => !readAlerts.includes(a.id));
        setAlertCount(unread.length);
      } catch { /* ignore */ }
    } catch (error) {
      console.error('Failed to fetch data:', error);
    }
  };

  const connectWebSocket = () => {
    if (!token) {
      setIsConnected(false);
      return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    ws.current = new WebSocket(`${protocol}//${host}/ws/dashboard?token=${encodeURIComponent(token)}&channels=inventory,orders,sales,alerts,audit,notifications`);

    ws.current.onopen = () => setIsConnected(true);
    ws.current.onclose = () => {
      setIsConnected(false);
      setTimeout(connectWebSocket, 3000);
    };
    ws.current.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);

        // Channel-based events from /ws/dashboard
        if (message.channel === 'audit') {
          setLogs(prev => [message.data, ...prev].slice(0, 100));
        }

        // Inventory changes — refresh dashboard data
        if (message.channel === 'inventory') {
          window.dispatchEvent(new CustomEvent('retailos:data-changed'));
        }

        // New sale completed — refresh stats
        if (message.channel === 'sales') {
          window.dispatchEvent(new CustomEvent('retailos:data-changed'));
        }

        // Order lifecycle events — refresh orders
        if (message.channel === 'orders') {
          window.dispatchEvent(new CustomEvent('retailos:data-changed'));
        }

        // Approval and alert events — refresh approvals + alerts
        if (message.channel === 'alerts') {
          fetchData();
        }

        // Legacy format fallback (from /ws/events broadcast_log)
        if (message.type === 'audit_log') {
          setLogs(prev => [message.data, ...prev].slice(0, 100));
          if (['owner_approved', 'owner_rejected', 'approval_requested'].includes(message.data?.event_type)) {
            fetchData();
          }
        }
      } catch {
        // ignore malformed messages
      }
    };
  };

  const headerMap = {
    home: {
      title: 'Dashboard',
      subtitle: 'Real-time overview of your store operations',
    },
    customers: {
      title: 'Customers',
      subtitle: 'Personalized profiles, purchase history, and recommendations',
    },
    orders: {
      title: 'Orders',
      subtitle: 'Track all customer and vendor orders with itemized pricing',
    },
    financials: {
      title: 'Financials',
      subtitle: 'Revenue, procurement costs, profit margins, and outstanding balances',
    },
    assistant: {
      title: 'Customer Bot',
      subtitle: 'Customer-facing product lookup for shelves, stock, and store hours',
    },
    plans: {
      title: 'Execution Plans',
      subtitle: 'Track the UI upgrade and custom user workspace rollout',
    },
    inventory: {
      title: 'Inventory',
      subtitle: 'Real-time stock levels and alerts',
    },
    cart: {
      title: 'Cart',
      subtitle: 'Record in-store sales and update stock in one flow',
    },
    shelves: {
      title: 'Shelf Tracker',
      subtitle: 'Zone occupancy, product placement, and AI shelf suggestions',
    },
    delivery: {
      title: 'Delivery Queue',
      subtitle: 'Customer delivery requests — direct, no middleman fees',
    },
    suppliers: {
      title: 'Suppliers',
      subtitle: 'Manage your supplier network and trust scores',
    },
    workspace: {
      title: 'User Workspace',
      subtitle: 'A custom setup built around how the user actually works',
    },
    voice: {
      title: 'Voice Assistant',
      subtitle: 'Talk to your store — ask about inventory, sales, suppliers, and more',
    },
    approvals: {
      title: 'Approvals',
      subtitle: `${approvals.length} pending decisions`,
    },
    history: {
      title: 'What Happened',
      subtitle: 'Complete audit trail of every action',
    },
    agents: {
      title: 'My Agents',
      subtitle: 'Your autonomous agent workforce',
    },
  };

  return (
    <div className="min-h-screen overflow-x-hidden text-stone-900">
      {!isKioskMode ? (
        <Sidebar 
          activeTab={activeTab} 
          setActiveTab={setActiveTab} 
          approvalCount={approvals.length}
          isConnected={isConnected}
        />
      ) : null}

      <header className={`sticky top-0 z-40 border-b border-black/5 backdrop-blur-xl ${isKioskMode ? 'bg-[rgba(255,252,247,0.88)]' : 'bg-[rgba(244,239,230,0.82)]'}`}>
        <div className="mx-auto max-w-[1500px] px-4 sm:px-6 lg:px-10">
          <div className="flex min-h-[84px] items-center justify-between gap-6">
            <div className="flex items-center gap-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-teal-700 to-amber-700 text-white shadow-lg shadow-teal-900/15">
                <Zap size={20} />
              </div>
              <div>
                <div className="font-display text-2xl font-bold tracking-tight">RetailOS</div>
                <div className="text-xs font-semibold uppercase tracking-[0.28em] text-stone-500">
                  {isKioskMode ? 'Customer kiosk' : 'Retail command center'}
                </div>
              </div>
            </div>

            {!isKioskMode ? (
              <div className="hidden min-w-0 flex-1 xl:flex xl:justify-center">
                <div className="scrollbar-hide flex max-w-full items-center gap-2 overflow-x-auto rounded-full border border-black/5 bg-white/50 px-2 py-2 shadow-sm">
                  {navItems.map((tab) => (
                    <button
                      key={tab.id}
                      onClick={() => setActiveTab(tab.id)}
                      className={`relative flex flex-shrink-0 items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition-all ${
                        activeTab === tab.id
                          ? 'bg-stone-900 text-white shadow-sm'
                          : 'text-stone-600 hover:bg-black/[0.04] hover:text-stone-900'
                      }`}
                    >
                      <tab.icon size={16} />
                      <span>{tab.label}</span>
                      {tab.badge > 0 && (
                        <span className="rounded-full bg-red-600 px-2 py-0.5 text-[10px] font-bold text-white">
                          {tab.badge}
                        </span>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="rounded-full border border-black/5 bg-white/70 px-4 py-2 text-sm font-semibold text-stone-600">
                Ask about shelves, stock, and recipes
              </div>
            )}

            <div className="flex items-center gap-3">
              {!isKioskMode ? (
                <div className="hidden sm:flex items-center gap-2 rounded-full border border-black/5 bg-white/55 px-4 py-2 text-sm">
                  <div className={`h-2.5 w-2.5 rounded-full ${!isOnline ? 'bg-amber-500' : isConnected ? 'bg-emerald-500' : 'bg-red-500'}`} />
                  <span className="font-medium text-stone-700">
                    {!isOnline
                      ? `Offline${pendingCount > 0 ? ` (${pendingCount} queued)` : ''}`
                      : isSyncing
                        ? 'Syncing...'
                        : isConnected
                          ? 'Live'
                          : 'Reconnecting'}
                  </span>
                  {!isOnline && pendingCount > 0 && (
                    <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-800">
                      {pendingCount}
                    </span>
                  )}
                </div>
              ) : null}
              <button 
                onClick={fetchData}
                className="rounded-full border border-black/5 bg-white/55 p-3 text-stone-600 transition-all hover:bg-white hover:text-stone-900"
                title="Refresh data"
              >
                <RefreshCw size={16} />
              </button>
              {!isKioskMode ? (
                <div className="relative">
                  <button
                    onClick={() => setShowAlerts(!showAlerts)}
                    className="rounded-full border border-black/5 bg-white/55 p-3 text-stone-600 transition-all hover:bg-white hover:text-stone-900"
                  >
                    <Bell size={16} />
                  </button>
                  {alertCount > 0 && (
                    <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-bold text-white">
                      {alertCount}
                    </span>
                  )}
                </div>
              ) : null}
              <div className={`xl:hidden rounded-full border border-black/5 bg-white/55 p-3 text-stone-600 ${isKioskMode ? 'hidden' : ''}`}>
                <Menu size={16} />
              </div>
            </div>
          </div>

          {!isKioskMode ? (
            <div className="xl:hidden overflow-x-auto pb-4 scrollbar-hide">
              <div className="flex min-w-max items-center gap-2">
                {navItems.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-semibold transition-all ${
                      activeTab === tab.id
                        ? 'border-stone-900 bg-stone-900 text-white'
                        : 'border-black/5 bg-white/55 text-stone-600 hover:bg-white'
                    }`}
                  >
                    <tab.icon size={15} />
                    <span>{tab.label}</span>
                    {tab.badge > 0 && (
                      <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${activeTab === tab.id ? 'bg-white/15 text-white' : 'bg-red-600 text-white'}`}>
                        {tab.badge}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </header>

      <main className={`mx-auto max-w-[1500px] overflow-x-hidden px-4 py-8 sm:px-6 lg:px-10 ${isKioskMode ? 'max-w-7xl' : ''}`}>
        <div className={`grid gap-8 ${isKioskMode ? '' : 'xl:grid-cols-[260px_minmax(0,1fr)]'}`}>
          {!isKioskMode ? (
            <aside className="hidden xl:block">
              <div className="sticky top-28">
                <div className="mb-6 rounded-[28px] border border-black/5 bg-white/55 p-6 shadow-[0_20px_60px_rgba(0,0,0,0.06)]">
                  <div className="text-xs font-black uppercase tracking-[0.22em] text-stone-500">Current View</div>
                  <h2 className="font-display mt-3 text-3xl font-bold tracking-tight text-stone-900">
                    {headerMap[activeTab]?.title || 'Dashboard'}
                  </h2>
                  <p className="mt-3 text-sm leading-relaxed text-stone-600">
                    {headerMap[activeTab]?.subtitle || 'Real-time overview of your store operations'}
                  </p>
                </div>
              </div>
            </aside>
          ) : null}

          <div className="min-w-0">
            {authRequired ? (
              <LoginForm onSuccess={() => { setAuthRequired(false); setRefreshTick((t) => t + 1); }} />
            ) : null}

            {!isKioskMode ? (
              <div className="mb-8 xl:hidden">
                <div className="text-xs font-black uppercase tracking-[0.22em] text-stone-500">Current View</div>
                <h2 className="font-display mt-2 text-3xl font-bold tracking-tight text-stone-900">
                  {headerMap[activeTab]?.title || 'Dashboard'}
                </h2>
                <p className="mt-2 text-sm text-stone-600">
                  {headerMap[activeTab]?.subtitle || 'Real-time overview of your store operations'}
                </p>
              </div>
            ) : null}
            
            <AnimatePresence mode="wait">
              <motion.div
                key={activeTab}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.2, ease: "easeOut" }}
              >
                {isKioskMode && (
                  <CustomerAssistantTab kioskMode />
                )}
                {!isKioskMode && activeTab === 'home' && (
                  <HomeTab 
                    stats={stats} 
                    logs={logs} 
                    refreshTick={refreshTick}
                    approvalCount={approvals.length}
                    plans={plans}
                    workspaceProfile={workspaceProfile}
                    onGoToApprovals={() => setActiveTab('approvals')}
                    onGoToPlans={() => setActiveTab('plans')}
                    onGoToWorkspace={() => setActiveTab('workspace')}
                  />
                )}
                {!isKioskMode && activeTab === 'plans' && (
                  <PlansTab plans={plans} />
                )}
                {!isKioskMode && activeTab === 'approvals' && (
                  <ApprovalsTab 
                    approvals={approvals} 
                    onRefresh={fetchData}
                  />
                )}
                {!isKioskMode && activeTab === 'history' && (
                  <WhatHappenedTab 
                    logs={logs} 
                  />
                )}
                {!isKioskMode && activeTab === 'agents' && (
                  <AgentsTab 
                    agents={agents} 
                    onRefresh={fetchData}
                  />
                )}
                {!isKioskMode && activeTab === 'customers' && (
                  <CustomersTab refreshTick={refreshTick} />
                )}
                {!isKioskMode && activeTab === 'orders' && (
                  <OrdersTab refreshTick={refreshTick} />
                )}
                {!isKioskMode && activeTab === 'financials' && (
                  <FinancialsTab refreshTick={refreshTick} />
                )}
                {!isKioskMode && activeTab === 'assistant' && (
                  <CustomerAssistantTab kioskMode={false} />
                )}
                {!isKioskMode && activeTab === 'inventory' && (
                  <InventoryTab />
                )}
                {!isKioskMode && activeTab === 'shelves' && (
                  <ShelfTrackerTab />
                )}
                {!isKioskMode && activeTab === 'delivery' && (
                  <DeliveryQueueTab refreshTick={refreshTick} />
                )}
                {!isKioskMode && activeTab === 'cart' && (
                  <CartTab refreshTick={refreshTick} />
                )}
                {!isKioskMode && activeTab === 'suppliers' && (
                  <SuppliersTab />
                )}
                {!isKioskMode && activeTab === 'staff' && (
                  <StaffTab />
                )}
                {!isKioskMode && activeTab === 'payments' && (
                  <PaymentsTab />
                )}
                {!isKioskMode && activeTab === 'loyalty' && (
                  <LoyaltyTab />
                )}
                {!isKioskMode && activeTab === 'scanner' && (
                  <BarcodeScannerTab />
                )}
                {!isKioskMode && activeTab === 'voice' && (
                  <VoiceAssistantTab />
                )}
                {!isKioskMode && activeTab === 'workspace' && (
                  <WorkspaceTab
                    plans={plans}
                    workspaceProfile={workspaceProfile}
                  />
                )}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </main>

      {!isKioskMode ? (
        <AlertsPanel
          open={showAlerts}
          onClose={() => setShowAlerts(false)}
          onNavigate={(tab) => { setActiveTab(tab); setShowAlerts(false); }}
          onAlertCountChange={setAlertCount}
        />
      ) : null}
    </div>
  );
}
