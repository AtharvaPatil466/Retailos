import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { 
  Package, 
  Search, 
  MessageCircle, 
  Megaphone, 
  BarChart3,
  Settings,
  Pause,
  Play,
  CheckCircle2,
  AlertCircle,
  Zap,
  Calendar
} from 'lucide-react';

const AGENTS = {
  'inventory': { 
    name: 'Stock Watcher', 
    role: 'Checks all 1,200 products every 60 seconds and alerts when anything is running low',
    icon: Package,
    color: 'text-amber-500',
    bg: 'bg-amber-500/10',
    gradient: 'from-amber-500/20 to-orange-500/5'
  },
  'procurement': { 
    name: 'Deal Finder', 
    role: 'Scours the market for the best prices and identifies the most reliable suppliers for you',
    icon: Search,
    color: 'text-blue-500',
    bg: 'bg-blue-500/10',
    gradient: 'from-blue-500/20 to-cyan-500/5'
  },
  'negotiation': { 
    name: 'Supplier Talker', 
    role: 'Handles all the WhatsApp back-and-forth with suppliers to lock in the deals you want',
    icon: MessageCircle,
    color: 'text-green-500',
    bg: 'bg-green-500/10',
    gradient: 'from-green-500/20 to-emerald-500/5'
  },
  'customer': { 
    name: 'Offer Sender', 
    role: 'Finds your best customers and sends them personalized special offers they actually like',
    icon: Megaphone,
    color: 'text-purple-500',
    bg: 'bg-purple-500/10',
    gradient: 'from-purple-500/20 to-pink-500/5'
  },
  'analytics': { 
    name: 'Business Analyst', 
    role: 'Analyzes your sales and orders to give you clear advice on how to grow your supermart',
    icon: BarChart3,
    color: 'text-blue-400',
    bg: 'bg-blue-400/10',
    gradient: 'from-blue-400/20 to-indigo-500/5'
  },
};

export default function AgentsTab({ agents, onRefresh }) {
  const [isTriggering, setIsTriggering] = useState(false);

  const toggleAgent = async (name, currentState) => {
    const endpoint = currentState === 'running' ? 'pause' : 'resume';
    try {
      await fetch(`/api/skills/${name}/${endpoint}`, { method: 'POST' });
      onRefresh();
    } catch (e) {
      console.error('Failed to toggle agent:', e);
    }
  };

  const triggerDemo = async () => {
    setIsTriggering(true);
    try {
      await fetch('/api/demo/trigger-flow', { method: 'POST' });
      alert("✅ Demo triggered! Go to Dashboard to see it starting.");
    } catch (e) {
      console.error('Failed to trigger demo:', e);
    }
    setIsTriggering(false);
  };

  return (
    <div className="space-y-6 lg:space-y-8">
      <div className="flex items-center justify-between px-1">
        <h2 className="text-xs font-black uppercase tracking-widest text-stone-500">Your RetailOS Team</h2>
        <div className="text-[10px] font-bold uppercase tracking-tighter text-stone-500">
          {Object.keys(AGENTS).length} Active Agents
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4 lg:gap-5">
        {Object.entries(AGENTS).map(([key, config], i) => {
          const status = agents.find(a => a.name === key)?.status || 'stopped';
          const isRunning = status === 'running';

          return (
            <motion.div
              key={key}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.08 }}
              className="group relative overflow-hidden rounded-[30px] border border-black/5 bg-[rgba(255,252,247,0.92)] p-5 text-stone-900 shadow-[0_20px_55px_rgba(0,0,0,0.06)] transition-all hover:bg-white lg:p-6"
            >
              <div className={`absolute inset-0 bg-gradient-to-br ${config.gradient} opacity-0 group-hover:opacity-100 transition-opacity duration-500`} />

              <div className="flex gap-4 items-start relative z-10">
                <div className={`flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-2xl ${config.bg} shadow-sm lg:h-14 lg:w-14`}>
                  <config.icon size={24} className={config.color} />
                </div>
                
                <div className="flex-1 space-y-1">
                  <div className="flex items-center justify-between">
                    <h3 className="text-[15px] font-black leading-none text-stone-900 lg:text-[16px]">{config.name}</h3>
                    <div className="flex items-center gap-1.5 rounded-full border border-black/10 bg-white/85 px-2 py-0.5">
                      <div className={`h-1.5 w-1.5 rounded-full ${isRunning ? 'bg-emerald-600 animate-pulse' : 'bg-stone-400'}`} />
                      <span className="text-[9px] font-black uppercase tracking-widest text-stone-500">
                        {isRunning ? 'Working' : 'Paused'}
                      </span>
                    </div>
                  </div>
                  
                  <p className="text-[11px] font-medium leading-tight text-stone-600 lg:text-[12px]">
                    {config.role}
                  </p>
                </div>
              </div>

              <div className="relative z-10 mt-4 flex items-center justify-between border-t border-black/5 pt-4">
                <div className="flex items-center gap-4">
                  <div className="space-y-0.5">
                    <div className="text-[8px] font-black uppercase tracking-widest text-stone-500">Today's Work</div>
                    <div className="flex items-center gap-1 text-[11px] font-black text-stone-900">
                      <Zap size={10} className="text-teal-700" />
                      {key === 'inventory' ? '720 checks' : 
                       key === 'procurement' ? '8 suppliers found' :
                       key === 'negotiation' ? '4 deals closed' : 
                       key === 'customer' ? '23 offers sent' :
                       key === 'analytics' ? '3 insights' :
                       'No alerts today'}
                    </div>
                  </div>
                  <div className="h-6 w-px bg-black/8" />
                  <div className="space-y-0.5">
                    <div className="text-[8px] font-black uppercase tracking-widest text-stone-500">Efficiency</div>
                    <div className="text-[11px] font-black text-stone-700">98.2%</div>
                  </div>
                </div>

                <button 
                  onClick={() => toggleAgent(key, status)}
                  className={`p-2.5 rounded-xl border transition-all ${
                    isRunning 
                      ? 'border-black/10 bg-white/85 text-stone-500 hover:bg-white hover:text-stone-900' 
                      : 'border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
                  }`}
                >
                  {isRunning ? <Pause size={14} /> : <Play size={14} />}
                </button>
              </div>
            </motion.div>
          );
        })}
      </div>

      <div className="pt-6 lg:pt-10 pb-4 flex flex-col items-center gap-4">
        <div className="text-[10px] font-black uppercase tracking-[0.3em] italic text-stone-400">Advanced Control</div>
        <button
          onClick={triggerDemo}
          disabled={isTriggering}
          className="flex items-center gap-2 rounded-2xl border border-black/10 bg-white/85 px-6 py-3 text-[10px] font-black uppercase tracking-widest text-stone-700 transition-all hover:bg-white hover:text-stone-900 disabled:opacity-50"
        >
          {isTriggering ? '🚀 Launching...' : '🚀 Launch Low Stock Demo'}
        </button>
      </div>
    </div>
  );
}
