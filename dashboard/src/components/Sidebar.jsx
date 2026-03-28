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
  Package,
  FolderKanban,
  Briefcase,
  ShoppingCart
} from 'lucide-react';

export default function Sidebar({ activeTab, setActiveTab, approvalCount, isConnected }) {
  const navItems = [
    { id: 'home', label: 'Overview', icon: LayoutDashboard },
    { id: 'plans', label: 'Plans', icon: FolderKanban },
    { id: 'inventory', label: 'Inventory', icon: Package },
    { id: 'cart', label: 'Cart', icon: ShoppingCart },
    { id: 'workspace', label: 'Workspace', icon: Briefcase },
    { id: 'approvals', label: 'Approvals', icon: CheckCircle2, badge: approvalCount },
    { id: 'history', label: 'Activity', icon: History },
    { id: 'agents', label: 'Agents', icon: Users },
  ];

  return (
    <aside className="hidden">
      <div className="rounded-[28px] border border-black/5 bg-white/55 p-5 shadow-[0_20px_60px_rgba(0,0,0,0.06)]">
        <div className="mb-5 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-teal-700 to-amber-700 text-white shadow-lg shadow-teal-900/15">
            <Zap size={18} className="text-white" />
          </div>
          <div>
            <h1 className="font-display text-lg font-bold tracking-tight text-stone-900">RetailOS</h1>
            <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-stone-500">Navigation</p>
          </div>
        </div>

        <nav className="space-y-1">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`w-full flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-semibold transition-all relative group ${
                activeTab === item.id 
                  ? 'bg-stone-900 text-white shadow-lg shadow-stone-900/10' 
                  : 'text-stone-600 hover:text-stone-900 hover:bg-black/[0.04]'
              }`}
            >
              {activeTab === item.id && (
                <motion.div
                  layoutId="sidebarActive"
                  className="absolute left-2 top-1/2 -translate-y-1/2 h-7 w-1 rounded-r-full bg-amber-600"
                  transition={{ type: "spring", stiffness: 300, damping: 30 }}
                />
              )}
              <item.icon size={18} strokeWidth={activeTab === item.id ? 2.5 : 2} />
              <span>{item.label}</span>
              {item.badge > 0 && (
                <span className="ml-auto flex h-5 w-5 items-center justify-center rounded-full bg-red-600 text-[10px] font-bold text-white">
                  {item.badge}
                </span>
              )}
            </button>
          ))}
        </nav>

        <div className="mt-6 space-y-4">
          <div className="flex items-center gap-3 rounded-2xl border border-black/5 bg-black/[0.03] px-4 py-3">
            {isConnected ? (
              <>
                <div className="relative">
                  <Wifi size={14} className="text-emerald-600" />
                  <div className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-emerald-500 opacity-50 animate-ping" />
                </div>
                <div>
                  <div className="text-xs font-bold text-emerald-700">Connected</div>
                  <div className="text-[10px] text-stone-500">Real-time updates active</div>
                </div>
              </>
            ) : (
              <>
                <WifiOff size={14} className="text-red-600" />
                <div>
                  <div className="text-xs font-bold text-red-700">Disconnected</div>
                  <div className="text-[10px] text-stone-500">Reconnecting...</div>
                </div>
              </>
            )}
          </div>
          <div className="text-center">
            <span className="text-[10px] font-bold tracking-[0.18em] text-stone-400">v1.0.0 · RetailOS</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
