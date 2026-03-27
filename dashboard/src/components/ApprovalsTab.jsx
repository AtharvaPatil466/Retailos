import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Check, 
  X, 
  MessageCircle, 
  ChevronDown, 
  ChevronUp,
  AlertTriangle,
  ArrowRight,
  TrendingUp,
  Clock,
  ShieldCheck
} from 'lucide-react';

const PRODUCT_ICONS = {
  'SKU-001': '🍦',
  'SKU-002': '🧂',
  'SKU-003': '🍼',
  'SKU-004': '🍞',
  'SKU-005': '🥚',
};

export default function ApprovalsTab({ approvals, onRefresh }) {
  const [expandedThreads, setExpandedThreads] = useState({});
  const [negotiations, setNegotiations] = useState({});

  useEffect(() => {
    fetchNegotiations();
  }, [approvals]);

  const fetchNegotiations = async () => {
    try {
      const res = await fetch('/api/negotiations');
      const data = await res.json();
      setNegotiations(data.active || {});
    } catch (e) {
      console.error('Failed to fetch negotiations:', e);
    }
  };

  const toggleThread = (id) => {
    setExpandedThreads(prev => ({ ...prev, [id]: !prev[id] }));
  };

  const handleAction = async (id, type) => {
    try {
      const endpoint = type === 'approve' ? 'approve' : 'reject';
      await fetch(`/api/approvals/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approval_id: id })
      });
      onRefresh();
    } catch (e) {
      console.error(`Failed to ${type}:`, e);
    }
  };

  if (approvals.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 lg:py-32 text-center space-y-4 px-6">
        <div className="w-20 h-20 lg:w-24 lg:h-24 bg-emerald-500/10 rounded-full flex items-center justify-center text-emerald-400">
          <motion.div animate={{ y: [0, -5, 0] }} transition={{ repeat: Infinity, duration: 2 }}>
            <Check size={40} strokeWidth={3} />
          </motion.div>
        </div>
        <div>
          <h2 className="text-lg lg:text-xl font-black uppercase tracking-tight">Nothing needs your attention</h2>
          <p className="text-white/40 text-sm lg:text-base font-medium leading-normal mt-1">
            RetailOS is monitoring everything for you. Go grab a chai! ☕
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xs font-black text-white/40 uppercase tracking-widest px-1">RetailOS needs your decision</h2>
      
      {/* Grid: 1 col mobile, 2 cols desktop */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 lg:gap-6">
        {approvals.map((approval, i) => {
          const result = approval.result || {};
          const isInventory = approval.skill === "inventory";
          const topSupplier = result.top_supplier || result.parsed || {};
          
          let sku, productName;
          if (isInventory) {
              const alert = result.alerts && result.alerts.length > 0 ? result.alerts[0] : {};
              sku = alert.sku;
              productName = alert.product_name || "Unknown Product";
          } else {
              sku = result.sku || (approval.event?.data?.sku);
              productName = result.product || result.product_name || "Unknown Product";
          }
          
          const icon = PRODUCT_ICONS[sku] || '📦';
          const negId = result.negotiation_id;
          const thread = negotiations[negId]?.thread || [];
          const approvalReason = approval.reason || result.approval_reason || "I found a better price for this item!";

          return (
            <motion.div
              key={approval.id}
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: i * 0.1 }}
              className="rounded-3xl bg-zinc-900 border border-white/5 overflow-hidden shadow-2xl hover:border-white/10 transition-all flex flex-col"
            >
              {/* Header */}
              <div className="p-5 flex items-start gap-4 border-b border-white/5 bg-white/[0.02]">
                <span className="text-4xl">{icon}</span>
                <div className="flex-1 min-w-0">
                  <h3 className="text-lg font-black leading-none mb-1 truncate">{productName}</h3>
                  <p className="text-xs font-bold text-white/40 italic leading-snug">
                    {approvalReason}
                  </p>
                </div>
              </div>

              {isInventory ? (
                <div className="p-5 border-b border-white/5 space-y-4 flex-1">
                  <div className="flex items-center gap-2 text-amber-500">
                    <AlertTriangle size={16} />
                    <span className="text-xs font-black uppercase tracking-widest">Restock Needed</span>
                  </div>
                  <div className="text-sm font-medium text-white/70 leading-relaxed">
                    Stock limit breached. Would you like to launch the autonomous agents to restock this?
                  </div>
                  <div className="bg-white/[0.03] rounded-xl p-3 text-xs text-white/50 italic border border-white/5 shadow-inner">
                    <span className="font-bold text-emerald-400 not-italic mr-1">Action:</span> 
                    {result.approval_details?.action_plan || "Trigger autonomous procurement flow to find the best supplier."}
                  </div>
                </div>
              ) : (
                <div className="flex-1">
                  {/* Price Comparison */}
                  <div className="p-5 grid grid-cols-2 gap-4 relative">
                    <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-8 h-8 rounded-full bg-zinc-900 border border-white/10 flex items-center justify-center z-10">
                      <ArrowRight size={14} className="text-white/40" />
                    </div>

                    <div className="space-y-1">
                      <div className="text-[10px] font-black text-white/40 uppercase tracking-widest">Usual Price</div>
                      <div className="text-xl font-black text-white/40 line-through">₹195</div>
                      <div className="text-[10px] font-bold text-white/40">From MegaMart</div>
                    </div>

                    <div className="space-y-1 text-right">
                      <div className="text-[10px] font-black text-emerald-400 uppercase tracking-widest leading-none mb-1"> ✨ New Best Price</div>
                      <div className="text-2xl font-black text-emerald-400 tracking-tight leading-none mb-1">₹{topSupplier.price_per_unit || '---'}</div>
                      <div className="text-[10px] font-bold text-emerald-400/60">You save ₹2,500!</div>
                    </div>
                  </div>

                  {/* Supplier Stats */}
                  <div className="px-5 pb-5 grid grid-cols-3 gap-2">
                    <div className="p-2.5 rounded-xl bg-white/5 flex flex-col items-center justify-center text-center">
                      <ShieldCheck size={14} className="text-blue-400 mb-1" />
                      <span className="text-[9px] font-black uppercase tracking-tighter text-white/40 leading-none">Trust</span>
                      <span className="text-[12px] font-black mt-0.5 leading-none">94%</span>
                    </div>
                    <div className="p-2.5 rounded-xl bg-white/5 flex flex-col items-center justify-center text-center">
                      <Clock size={14} className="text-amber-400 mb-1" />
                      <span className="text-[9px] font-black uppercase tracking-tighter text-white/40 leading-none">Wait</span>
                      <span className="text-[12px] font-black mt-0.5 leading-none">1 Day</span>
                    </div>
                    <div className="p-2.5 rounded-xl bg-white/5 flex flex-col items-center justify-center text-center">
                      <TrendingUp size={14} className="text-emerald-400 mb-1" />
                      <span className="text-[9px] font-black uppercase tracking-tighter text-white/40 leading-none">Quality</span>
                      <span className="text-[12px] font-black mt-0.5 leading-none">AA+</span>
                    </div>
                  </div>
                </div>
              )}

              {/* Negotiation Thread */}
              {negId && (
                <div className="border-t border-white/5">
                  <button 
                    onClick={() => toggleThread(approval.id)}
                    className="w-full p-4 flex items-center justify-between text-white/40 hover:text-white transition-colors group"
                  >
                    <div className="flex items-center gap-2">
                      <MessageCircle size={16} />
                      <span className="text-[10px] font-black uppercase tracking-widest">See our WhatsApp talk</span>
                    </div>
                    {expandedThreads[approval.id] ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </button>
                  
                  <AnimatePresence>
                    {expandedThreads[approval.id] && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="overflow-hidden bg-black/40 px-4 pb-4"
                      >
                        <div className="pt-2 flex flex-col gap-3">
                          {thread.map((msg, mid) => (
                            <div key={mid} className={`flex flex-col ${msg.direction === 'outbound' ? 'items-end' : 'items-start'}`}>
                              <div className="text-[8px] font-black text-white/20 uppercase tracking-widest mb-1">
                                {msg.direction === 'outbound' ? 'RetailOS sent:' : 'Supplier replied:'}
                              </div>
                              <div className={msg.direction === 'outbound' ? 'whatsapp-bubble-out text-[13px] leading-snug' : 'whatsapp-bubble-in text-[13px] leading-snug'}>
                                {msg.message}
                              </div>
                              <div className="text-[9px] text-white/20 mt-1 font-medium">
                                {new Date(msg.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                              </div>
                            </div>
                          ))}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )}

              {/* Actions */}
              <div className="p-4 bg-white/[0.03] flex flex-col lg:flex-row gap-2">
                <motion.button
                  whileTap={{ scale: 0.98 }}
                  onClick={() => handleAction(approval.id, 'approve')}
                  className="btn-success w-full flex items-center justify-center gap-2"
                >
                  <Check size={20} strokeWidth={3} />
                  <span>YES, ORDER IT</span>
                </motion.button>
                <motion.button
                  whileTap={{ scale: 0.98 }}
                  onClick={() => handleAction(approval.id, 'reject')}
                  className="p-3 text-red-500 font-black text-xs uppercase tracking-widest hover:bg-red-500/10 rounded-xl transition-all lg:w-auto"
                >
                  ❌ No, skip
                </motion.button>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
