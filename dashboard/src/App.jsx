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
  ShoppingCart
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

export default function App() {
  const [activeTab, setActiveTab] = useState('home');
  const [logs, setLogs] = useState([]);
  const [approvals, setApprovals] = useState([]);
  const [agents, setAgents] = useState([]);
  const [stats, setStats] = useState({
    moneySaved: 8400,
    ordersPlaced: 6,
    offersSent: 147,
    hoursSaved: 12
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
  const [isConnected, setIsConnected] = useState(false);
  const ws = useRef(null);
  const navItems = [
    { id: 'home', label: 'Overview', icon: LayoutDashboard },
    { id: 'plans', label: 'Plans', icon: FolderKanban },
    { id: 'workspace', label: 'Workspace', icon: Briefcase },
    { id: 'inventory', label: 'Inventory', icon: Package },
    { id: 'cart', label: 'Cart', icon: ShoppingCart },
    { id: 'approvals', label: 'Approvals', icon: CheckCircle2, badge: approvals.length },
    { id: 'history', label: 'Activity', icon: History },
    { id: 'agents', label: 'Agents', icon: Users }
  ];

  useEffect(() => {
    fetchData();
    connectWebSocket();
    const interval = setInterval(fetchData, 30000);
    return () => {
      clearInterval(interval);
      if (ws.current) ws.current.close();
    };
  }, []);

  const fetchData = async () => {
    try {
      const [statusRes, approvalsRes, logsRes] = await Promise.all([
        fetch('/api/status'),
        fetch('/api/approvals'),
        fetch('/api/audit?limit=100')
      ]);
      
      const statusData = await statusRes.json();
      const approvalsData = await approvalsRes.json();
      const logsData = await logsRes.json();

      setAgents(statusData.skills || []);
      setApprovals(approvalsData || []);
      setLogs(logsData || []);
    } catch (error) {
      console.error('Failed to fetch data:', error);
    }
  };

  const connectWebSocket = () => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    ws.current = new WebSocket(`${protocol}//${host}/ws/events`);

    ws.current.onopen = () => setIsConnected(true);
    ws.current.onclose = () => {
      setIsConnected(false);
      setTimeout(connectWebSocket, 3000);
    };
    ws.current.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.type === 'audit_log') {
        setLogs(prev => [message.data, ...prev].slice(0, 100));
        if (['owner_approved', 'owner_rejected', 'approval_requested'].includes(message.data.event_type)) {
          fetchData();
        }
      }
    };
  };

  const headerMap = {
    home: {
      title: 'Dashboard',
      subtitle: 'Real-time overview of your store operations',
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
    workspace: {
      title: 'User Workspace',
      subtitle: 'A custom setup built around how the user actually works',
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
    <div className="min-h-screen text-stone-900">
      <Sidebar 
        activeTab={activeTab} 
        setActiveTab={setActiveTab} 
        approvalCount={approvals.length}
        isConnected={isConnected}
      />

      <header className="sticky top-0 z-40 border-b border-black/5 bg-[rgba(244,239,230,0.82)] backdrop-blur-xl">
        <div className="mx-auto max-w-[1500px] px-4 sm:px-6 lg:px-10">
          <div className="flex min-h-[84px] items-center justify-between gap-6">
            <div className="flex items-center gap-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-teal-700 to-amber-700 text-white shadow-lg shadow-teal-900/15">
                <Zap size={20} />
              </div>
              <div>
                <div className="font-display text-2xl font-bold tracking-tight">RetailOS</div>
                <div className="text-xs font-semibold uppercase tracking-[0.28em] text-stone-500">
                  Retail command center
                </div>
              </div>
            </div>

            <div className="hidden xl:flex items-center gap-2 rounded-full border border-black/5 bg-white/50 px-2 py-2 shadow-sm">
              {navItems.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`relative flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition-all ${
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

            <div className="flex items-center gap-3">
              <div className="hidden sm:flex items-center gap-2 rounded-full border border-black/5 bg-white/55 px-4 py-2 text-sm">
                <div className={`h-2.5 w-2.5 rounded-full ${isConnected ? 'bg-emerald-500' : 'bg-red-500'}`} />
                <span className="font-medium text-stone-700">
                  {isConnected ? 'Live updates active' : 'Reconnecting'}
                </span>
              </div>
              <button 
                onClick={fetchData}
                className="rounded-full border border-black/5 bg-white/55 p-3 text-stone-600 transition-all hover:bg-white hover:text-stone-900"
                title="Refresh data"
              >
                <RefreshCw size={16} />
              </button>
              <div className="relative">
                <button className="rounded-full border border-black/5 bg-white/55 p-3 text-stone-600 transition-all hover:bg-white hover:text-stone-900">
                  <Bell size={16} />
                </button>
                {approvals.length > 0 && (
                  <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-bold text-white">
                    {approvals.length}
                  </span>
                )}
              </div>
              <div className="xl:hidden rounded-full border border-black/5 bg-white/55 p-3 text-stone-600">
                <Menu size={16} />
              </div>
            </div>
          </div>

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
        </div>
      </header>

      <main className="mx-auto max-w-[1500px] px-4 py-8 sm:px-6 lg:px-10">
        <div className="grid gap-8 xl:grid-cols-[260px_minmax(0,1fr)]">
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

          <div className="min-w-0">
            <div className="mb-8 xl:hidden">
              <div className="text-xs font-black uppercase tracking-[0.22em] text-stone-500">Current View</div>
              <h2 className="font-display mt-2 text-3xl font-bold tracking-tight text-stone-900">
                {headerMap[activeTab]?.title || 'Dashboard'}
              </h2>
              <p className="mt-2 text-sm text-stone-600">
                {headerMap[activeTab]?.subtitle || 'Real-time overview of your store operations'}
              </p>
            </div>
            
            <AnimatePresence mode="wait">
              <motion.div
                key={activeTab}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.2, ease: "easeOut" }}
              >
                {activeTab === 'home' && (
                  <HomeTab 
                    stats={stats} 
                    logs={logs} 
                    approvalCount={approvals.length}
                    plans={plans}
                    workspaceProfile={workspaceProfile}
                    onGoToApprovals={() => setActiveTab('approvals')}
                    onGoToPlans={() => setActiveTab('plans')}
                    onGoToWorkspace={() => setActiveTab('workspace')}
                  />
                )}
                {activeTab === 'plans' && (
                  <PlansTab plans={plans} />
                )}
                {activeTab === 'approvals' && (
                  <ApprovalsTab 
                    approvals={approvals} 
                    onRefresh={fetchData}
                  />
                )}
                {activeTab === 'history' && (
                  <WhatHappenedTab 
                    logs={logs} 
                  />
                )}
                {activeTab === 'agents' && (
                  <AgentsTab 
                    agents={agents} 
                    onRefresh={fetchData}
                  />
                )}
                {activeTab === 'inventory' && (
                  <InventoryTab />
                )}
                {activeTab === 'cart' && (
                  <CartTab />
                )}
                {activeTab === 'workspace' && (
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
    </div>
  );
}
