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
        <div className="flex h-20 w-20 items-center justify-center rounded-full bg-emerald-100 text-emerald-700 lg:h-24 lg:w-24">
          <motion.div animate={{ y: [0, -5, 0] }} transition={{ repeat: Infinity, duration: 2 }}>
            <Check size={40} strokeWidth={3} />
          </motion.div>
        </div>
        <div>
          <h2 className="text-lg lg:text-xl font-black uppercase tracking-tight text-stone-900">Nothing needs your attention</h2>
          <p className="mt-1 text-sm font-medium leading-normal text-stone-600 lg:text-base">
            RetailOS is monitoring everything for you. Go grab a chai! ☕
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h2 className="px-1 text-xs font-black uppercase tracking-widest text-stone-500">RetailOS needs your decision</h2>
      
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
              className="flex flex-col overflow-hidden rounded-[30px] border border-black/5 bg-[rgba(255,252,247,0.92)] text-stone-900 shadow-[0_20px_55px_rgba(0,0,0,0.06)] transition-all hover:bg-white"
            >
              <div className="flex items-start gap-4 border-b border-black/5 bg-white/75 p-5">
                <span className="text-4xl">{icon}</span>
                <div className="flex-1 min-w-0">
                  <h3 className="mb-1 truncate text-lg font-black leading-none text-stone-900">{productName}</h3>
                  <p className="text-xs font-bold italic leading-snug text-stone-600">
                    {approvalReason}
                  </p>
                </div>
              </div>

              {isInventory ? (
                <div className="flex-1 space-y-4 border-b border-black/5 p-5">
                  <div className="flex items-center gap-2 text-amber-700">
                    <AlertTriangle size={16} />
                    <span className="text-xs font-black uppercase tracking-widest">Restock Needed</span>
                  </div>
                  <div className="text-sm font-medium leading-relaxed text-stone-700">
                    Stock limit breached. Would you like to launch the autonomous agents to restock this?
                  </div>
                  <div className="rounded-xl border border-black/5 bg-white/85 p-3 text-xs italic text-stone-600 shadow-sm">
                    <span className="mr-1 font-bold not-italic text-emerald-700">Action:</span> 
                    {result.approval_details?.action_plan || "Trigger autonomous procurement flow to find the best supplier."}
                  </div>
                </div>
              ) : (
                <div className="flex-1">
                  <div className="p-5 grid grid-cols-2 gap-4 relative">
                    <div className="absolute left-1/2 top-1/2 z-10 flex h-8 w-8 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-black/10 bg-stone-100">
                      <ArrowRight size={14} className="text-stone-500" />
                    </div>

                    <div className="space-y-1">
                      <div className="text-[10px] font-black uppercase tracking-widest text-stone-500">Usual Price</div>
                      <div className="text-xl font-black text-stone-500 line-through">₹195</div>
                      <div className="text-[10px] font-bold text-stone-500">From MegaMart</div>
                    </div>

                    <div className="space-y-1 text-right">
                      <div className="mb-1 text-[10px] font-black uppercase tracking-widest leading-none text-emerald-700">New Best Price</div>
                      <div className="mb-1 text-2xl font-black leading-none tracking-tight text-emerald-700">₹{topSupplier.price_per_unit || '---'}</div>
                      <div className="text-[10px] font-bold text-emerald-700/70">You save ₹2,500!</div>
                    </div>
                  </div>

                  <div className="px-5 pb-5 grid grid-cols-3 gap-2">
                    <div className="flex flex-col items-center justify-center rounded-xl border border-black/5 bg-white/85 p-2.5 text-center shadow-sm">
                      <ShieldCheck size={14} className="mb-1 text-teal-700" />
                      <span className="text-[9px] font-black uppercase tracking-tighter leading-none text-stone-500">Trust</span>
                      <span className="mt-0.5 text-[12px] font-black leading-none text-stone-900">94%</span>
                    </div>
                    <div className="flex flex-col items-center justify-center rounded-xl border border-black/5 bg-white/85 p-2.5 text-center shadow-sm">
                      <Clock size={14} className="mb-1 text-amber-700" />
                      <span className="text-[9px] font-black uppercase tracking-tighter leading-none text-stone-500">Wait</span>
                      <span className="mt-0.5 text-[12px] font-black leading-none text-stone-900">1 Day</span>
                    </div>
                    <div className="flex flex-col items-center justify-center rounded-xl border border-black/5 bg-white/85 p-2.5 text-center shadow-sm">
                      <TrendingUp size={14} className="mb-1 text-emerald-700" />
                      <span className="text-[9px] font-black uppercase tracking-tighter leading-none text-stone-500">Quality</span>
                      <span className="mt-0.5 text-[12px] font-black leading-none text-stone-900">AA+</span>
                    </div>
                  </div>
                </div>
              )}

              {negId && (
                <div className="border-t border-black/5">
                  <button 
                    onClick={() => toggleThread(approval.id)}
                    className="group flex w-full items-center justify-between p-4 text-stone-600 transition-colors hover:text-stone-900"
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
                        className="overflow-hidden bg-stone-50 px-4 pb-4"
                      >
                        <div className="pt-2 flex flex-col gap-3">
                          {thread.map((msg, mid) => (
                            <div key={mid} className={`flex flex-col ${msg.direction === 'outbound' ? 'items-end' : 'items-start'}`}>
                              <div className="mb-1 text-[8px] font-black uppercase tracking-widest text-stone-500">
                                {msg.direction === 'outbound' ? 'RetailOS sent:' : 'Supplier replied:'}
                              </div>
                              <div className={msg.direction === 'outbound' ? 'whatsapp-bubble-out text-[13px] leading-snug' : 'whatsapp-bubble-in text-[13px] leading-snug'}>
                                {msg.message}
                              </div>
                              <div className="mt-1 text-[9px] font-medium text-stone-500">
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

              <div className="flex flex-col gap-2 bg-stone-50 p-4 lg:flex-row">
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
                  className="rounded-xl p-3 text-xs font-black uppercase tracking-widest text-red-700 transition-all hover:bg-red-50 lg:w-auto"
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
