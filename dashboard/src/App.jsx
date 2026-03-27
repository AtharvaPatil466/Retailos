import React, { useState, useEffect, useRef } from 'react';
import { 
  LayoutDashboard, 
  CheckCircle2, 
  History, 
  Users, 
  Bell,
  ArrowRight,
  RefreshCw,
  Zap,
  Package
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import Sidebar from './components/Sidebar';
import HomeTab from './components/HomeTab';
import ApprovalsTab from './components/ApprovalsTab';
import WhatHappenedTab from './components/WhatHappenedTab';
import AgentsTab from './components/AgentsTab';
import InventoryTab from './components/InventoryTab';

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
  const [isConnected, setIsConnected] = useState(false);
  const ws = useRef(null);

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

  const mobileTabs = [
    { id: 'home', label: 'HOME', icon: LayoutDashboard },
    { id: 'inventory', label: 'INVENTORY', icon: Package },
    { id: 'approvals', label: 'APPROVALS', icon: CheckCircle2, badge: approvals.length },
    { id: 'history', label: 'HISTORY', icon: History },
    { id: 'agents', label: 'AGENTS', icon: Users },
  ];

  return (
    <div className="min-h-screen bg-black text-white">
      {/* Desktop Sidebar */}
      <Sidebar 
        activeTab={activeTab} 
        setActiveTab={setActiveTab} 
        approvalCount={approvals.length}
        isConnected={isConnected}
      />

      {/* Mobile Top Nav — hidden on desktop */}
      <nav className="lg:hidden sticky top-0 z-50 bg-[#0a0a0a]/90 backdrop-blur-xl border-b border-white/5 px-4 pt-6 pb-2">
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
              <Zap size={16} className="text-white" />
            </div>
            <h1 className="text-xl font-black tracking-tighter">RetailOS</h1>
          </div>
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
            <span className="text-[10px] font-bold text-white/40 uppercase tracking-widest leading-none">
              {isConnected ? 'Live' : 'Offline'}
            </span>
          </div>
        </div>
        
        <div className="flex items-center justify-between">
          {mobileTabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex flex-col items-center gap-1.5 pb-2 transition-all relative ${
                activeTab === tab.id ? 'text-blue-500' : 'text-white/40 hover:text-white/60'
              }`}
            >
              <tab.icon size={20} strokeWidth={activeTab === tab.id ? 2.5 : 2} />
              <span className="text-[10px] font-black tracking-wider uppercase">
                {tab.label}
              </span>
              {tab.badge > 0 && (
                <span className="absolute -top-1 -right-1 bg-red-500 text-white text-[9px] font-bold w-4 h-4 rounded-full flex items-center justify-center">
                  {tab.badge}
                </span>
              )}
              {activeTab === tab.id && (
                <motion.div 
                  layoutId="activeTabMobile" 
                  className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-500" 
                />
              )}
            </button>
          ))}
        </div>
      </nav>

      {/* Desktop Header Bar — hidden on mobile */}
      <header className="hidden lg:flex fixed top-0 left-64 right-0 z-40 h-16 bg-[#0a0a0a]/80 backdrop-blur-xl border-b border-white/5 items-center justify-between px-8">
        <div>
          <h2 className="text-lg font-black capitalize tracking-tight">
            {activeTab === 'home' ? 'Dashboard' : activeTab === 'history' ? 'What Happened' : activeTab === 'agents' ? 'My Agents' : activeTab === 'inventory' ? 'Inventory' : 'Approvals'}
          </h2>
          <p className="text-[11px] text-white/30 font-medium -mt-0.5">
            {activeTab === 'home' ? 'Real-time overview of your store operations' : 
             activeTab === 'approvals' ? `${approvals.length} pending decisions` :
             activeTab === 'history' ? 'Complete audit trail of every action' :
             activeTab === 'inventory' ? 'Real-time stock levels and alerts' :
             'Your autonomous agent workforce'}
          </p>
        </div>
        <div className="flex items-center gap-4">
          <button 
            onClick={fetchData}
            className="p-2.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/5 text-white/40 hover:text-white transition-all"
            title="Refresh data"
          >
            <RefreshCw size={16} />
          </button>
          <div className="relative">
            <button className="p-2.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/5 text-white/40 hover:text-white transition-all">
              <Bell size={16} />
            </button>
            {approvals.length > 0 && (
              <span className="absolute -top-1 -right-1 bg-red-500 text-white text-[9px] font-bold w-4 h-4 rounded-full flex items-center justify-center animate-pulse">
                {approvals.length}
              </span>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="lg:ml-64 lg:pt-16">
        <div className="p-4 lg:p-8 pb-24 lg:pb-8 overflow-x-hidden">
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
                  onGoToApprovals={() => setActiveTab('approvals')}
                />
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
            </motion.div>
          </AnimatePresence>
        </div>
      </main>
    </div>
  );
}
