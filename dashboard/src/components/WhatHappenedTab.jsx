import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  ShoppingCart, 
  Megaphone, 
  MessageCircle, 
  Search, 
  CheckCircle,
  Clock,
  ChevronDown,
  ChevronUp,
  BrainCircuit,
  Calendar,
  Filter
} from 'lucide-react';

const CATEGORIES = {
  'inventory': { label: 'Stock Checks', icon: Search, color: 'text-amber-500', bg: 'bg-amber-500/10' },
  'procurement': { label: 'Supplier Finder', icon: ShoppingCart, color: 'text-blue-500', bg: 'bg-blue-500/10' },
  'negotiation': { label: 'Supplier Talks', icon: MessageCircle, color: 'text-green-500', bg: 'bg-green-500/10' },
  'customer': { label: 'Offers Sent', icon: Megaphone, color: 'text-purple-500', bg: 'bg-purple-500/10' },
  'orchestrator': { label: 'System', icon: BrainCircuit, color: 'text-white/40', bg: 'bg-white/5' },
};

export default function WhatHappenedTab({ logs }) {
  const [filter, setFilter] = useState('All');
  const [expandedLogs, setExpandedLogs] = useState({});

  const toggleLog = (id) => {
    setExpandedLogs(prev => ({ ...prev, [id]: !prev[id] }));
  };

  const filteredLogs = logs.filter(log => {
    if (filter === 'All') return true;
    const cat = CATEGORIES[log.skill]?.label;
    return cat === filter;
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between px-1">
        <h2 className="text-xs font-black uppercase tracking-widest text-stone-500">Everything RetailOS did</h2>
        <div className="hidden lg:flex items-center gap-1.5 text-[10px] font-bold text-stone-500">
          <Filter size={10} />
          <span>{filteredLogs.length} events</span>
        </div>
      </div>

      <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide lg:flex-wrap">
        {['All', 'Stock Checks', 'Supplier Finder', 'Supplier Talks', 'Offers Sent'].map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-4 py-2 rounded-full text-[10px] font-black uppercase tracking-widest whitespace-nowrap border transition-all ${
              filter === f 
                ? 'border-teal-700 bg-teal-700 text-white shadow-lg shadow-teal-700/15' 
                : 'border-black/10 bg-white/80 text-stone-600 hover:border-black/15 hover:text-stone-900'
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {/* Timeline */}
      <div className="space-y-3 lg:space-y-4">
        {filteredLogs.map((log, i) => {
          const category = CATEGORIES[log.skill] || CATEGORIES.orchestrator;
          const Icon = category.icon;
          const isExpanded = expandedLogs[log.id];

          return (
            <motion.div
              key={log.id}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: Math.min(i * 0.03, 0.3) }}
              className="group"
            >
              <div className="relative overflow-hidden rounded-2xl border border-black/5 bg-[rgba(255,252,247,0.9)] shadow-[0_18px_45px_rgba(0,0,0,0.05)] transition-all hover:bg-white lg:rounded-3xl">
                <div className="p-4 lg:p-5 flex gap-3 lg:gap-4">
                  <div className={`w-10 h-10 lg:w-12 lg:h-12 rounded-xl lg:rounded-2xl ${category.bg} flex items-center justify-center flex-shrink-0`}>
                    <Icon size={18} className={category.color} />
                  </div>
                  
                  <div className="flex-1 min-w-0 space-y-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className={`text-[10px] font-black uppercase tracking-widest ${category.color}`}>
                        {category.label}
                      </span>
                      <span className="flex flex-shrink-0 items-center gap-1 text-[10px] font-bold uppercase tracking-widest text-stone-500">
                        <Calendar size={10} />
                        {new Date(log.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                    
                    <h3 className="text-[13px] font-black leading-tight text-stone-900 transition-colors group-hover:text-teal-700 lg:text-[14px]">
                      {log.decision}
                    </h3>
                    
                    <p className="line-clamp-2 text-[11px] font-medium leading-snug text-stone-600 lg:text-[12px]">
                      {log.reasoning}
                    </p>

                    <button 
                      onClick={() => toggleLog(log.id)}
                      className="mt-2 flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest text-teal-700/80 transition-colors hover:text-teal-700"
                    >
                      <BrainCircuit size={12} />
                      <span>{isExpanded ? 'Hide thinking' : 'How did you decide this?'}</span>
                      {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                    </button>
                  </div>
                </div>

                <AnimatePresence>
                  {isExpanded && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="border-t border-black/5 bg-stone-50"
                    >
                      <div className="p-5 space-y-3">
                        <div className="text-[10px] font-black uppercase tracking-widest text-teal-700">Here's exactly how I thought about this:</div>
                        <div className="rounded-2xl border border-black/5 bg-white p-4 text-[12px] font-medium italic leading-relaxed text-stone-700">
                          "{log.reasoning || "I checked the current data and historical patterns to ensure the best possible outcome for your business."}"
                        </div>
                        {log.outcome && (
                          <div className="space-y-2">
                             <div className="text-[10px] font-black uppercase tracking-widest text-stone-500">Final Result:</div>
                             <div className="max-h-32 overflow-y-auto break-all rounded-xl border border-black/5 bg-white p-3 font-mono text-[11px] text-stone-600 scrollbar-thin">
                               {log.outcome}
                             </div>
                          </div>
                        )}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </motion.div>
          );
        })}

        {filteredLogs.length === 0 && (
          <div className="space-y-4 rounded-3xl border-2 border-dashed border-black/10 bg-white/60 px-10 py-20 text-center">
             <div className="text-center text-4xl opacity-40">📜</div>
             <p className="text-sm font-black uppercase tracking-widest leading-none text-stone-500">Nothing found in this list</p>
          </div>
        )}
      </div>
    </div>
  );
}
