import React from 'react';
import { motion } from 'framer-motion';
import { 
  LayoutDashboard, 
  CheckCircle2, 
  History, 
  Users, 
  Zap,
  Wifi,
  WifiOff,
  Package
} from 'lucide-react';

export default function Sidebar({ activeTab, setActiveTab, approvalCount, isConnected }) {
  const navItems = [
    { id: 'home', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'inventory', label: 'Inventory', icon: Package },
    { id: 'approvals', label: 'Approvals', icon: CheckCircle2, badge: approvalCount },
    { id: 'history', label: 'What Happened', icon: History },
    { id: 'agents', label: 'My Agents', icon: Users },
  ];

  return (
    <aside className="hidden lg:flex lg:flex-col fixed top-0 left-0 bottom-0 w-64 bg-[#0a0a0a] border-r border-white/5 z-50">
      {/* Brand */}
      <div className="px-6 pt-8 pb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
            <Zap size={20} className="text-white" />
          </div>
          <div>
            <h1 className="text-lg font-black tracking-tight text-white">RetailOS</h1>
            <p className="text-[10px] font-bold text-white/30 uppercase tracking-widest">Autonomous Runtime</p>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 space-y-1">
        <div className="px-3 mb-4">
          <span className="text-[10px] font-black text-white/20 uppercase tracking-[0.2em]">Navigation</span>
        </div>
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => setActiveTab(item.id)}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-semibold transition-all relative group ${
              activeTab === item.id 
                ? 'bg-white/[0.08] text-white shadow-lg shadow-black/20' 
                : 'text-white/40 hover:text-white/70 hover:bg-white/[0.03]'
            }`}
          >
            {activeTab === item.id && (
              <motion.div
                layoutId="sidebarActive"
                className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-blue-500 rounded-r-full"
                transition={{ type: "spring", stiffness: 300, damping: 30 }}
              />
            )}
            <item.icon size={18} strokeWidth={activeTab === item.id ? 2.5 : 2} />
            <span>{item.label}</span>
            {item.badge > 0 && (
              <span className="ml-auto bg-red-500 text-white text-[10px] font-bold w-5 h-5 rounded-full flex items-center justify-center animate-pulse">
                {item.badge}
              </span>
            )}
          </button>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-4 pb-6 space-y-4">
        {/* Connection Status */}
        <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-white/[0.03] border border-white/5">
          {isConnected ? (
            <>
              <div className="relative">
                <Wifi size={14} className="text-green-400" />
                <div className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-green-400 rounded-full animate-ping opacity-50" />
              </div>
              <div>
                <div className="text-xs font-bold text-green-400">Connected</div>
                <div className="text-[10px] text-white/20">Real-time updates active</div>
              </div>
            </>
          ) : (
            <>
              <WifiOff size={14} className="text-red-400" />
              <div>
                <div className="text-xs font-bold text-red-400">Disconnected</div>
                <div className="text-[10px] text-white/20">Reconnecting...</div>
              </div>
            </>
          )}
        </div>

        {/* Version */}
        <div className="text-center">
          <span className="text-[10px] font-bold text-white/10 tracking-widest">v1.0.0 · RetailOS</span>
        </div>
      </div>
    </aside>
  );
}
