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
  ShieldCheck,
  LayoutGrid,
  MoveRight,
  Sparkles
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
      <div className="flex flex-col items-center justify-center px-6 py-20 text-center space-y-4 lg:py-32">
        <div className="flex h-20 w-20 items-center justify-center rounded-md bg-[rgba(139,211,212,0.14)] text-[#8bd3d4] lg:h-24 lg:w-24">
          <motion.div animate={{ y: [0, -5, 0] }} transition={{ repeat: Infinity, duration: 2 }}>
            <Check size={40} strokeWidth={3} />
          </motion.div>
        </div>
        <div>
          <h2 className="atelier-label text-lg tracking-tight text-[var(--text)] lg:text-xl">Nothing needs your attention</h2>
          <p className="mt-1 text-sm font-medium leading-normal text-[var(--text-muted)] lg:text-base">
            RetailOS is monitoring everything for you. Go grab a chai! ☕
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <h2 className="atelier-label px-1 text-[10px] text-[#8bd3d4]">RetailOS needs your decision</h2>
      
      {/* Grid: 1 col mobile, 2 cols desktop */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 lg:gap-6">
        {approvals.map((approval, i) => {
          const result = approval.result || {};
          const isInventory = approval.skill === "inventory";
          const isShelfOpt = result.approval_details?.type === "shelf_optimization" || approval.skill === "shelf_manager";
          const topSupplier = result.top_supplier || result.parsed || {};

          let sku, productName;
          if (isShelfOpt) {
              sku = null;
              productName = "Shelf Optimization";
          } else if (isInventory) {
              const alert = result.alerts && result.alerts.length > 0 ? result.alerts[0] : {};
              sku = alert.sku;
              productName = alert.product_name || "Unknown Product";
          } else {
              sku = result.sku || (approval.event?.data?.sku);
              productName = result.product || result.product_name || "Unknown Product";
          }

          const icon = isShelfOpt ? '🗂️' : (PRODUCT_ICONS[sku] || '📦');
          const negId = result.negotiation_id;
          const thread = negotiations[negId]?.thread || [];
          const approvalReason = approval.reason || result.approval_reason || "I found a better price for this item!";

          return (
            <motion.div
              key={approval.id}
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: i * 0.1 }}
              className="flex flex-col overflow-hidden rounded-lg atelier-panel text-[var(--text)] shadow-[0_28px_70px_rgba(0,0,0,0.18)] transition-all hover:bg-[rgba(55,58,56,0.72)]"
            >
              <div className="flex items-start gap-4 border-b border-[rgba(67,72,72,0.18)] bg-[rgba(12,15,14,0.18)] p-5">
                <span className="text-4xl">{icon}</span>
                <div className="flex-1 min-w-0">
                  <h3 className="font-display mb-1 truncate text-3xl font-light italic leading-none text-[var(--text)]">{productName}</h3>
                  <p className="text-xs font-bold italic leading-snug text-[var(--text-muted)]">
                    {approvalReason}
                  </p>
                </div>
              </div>

              {isShelfOpt ? (
                <div className="flex-1 space-y-4 border-b border-[rgba(67,72,72,0.18)] p-5">
                  <div className="flex items-center gap-2 text-[#8bd3d4]">
                    <Sparkles size={16} />
                    <span className="atelier-label text-[10px]">AI Shelf Optimization</span>
                  </div>
                  <div className="text-sm font-medium leading-relaxed text-[var(--text-muted)]">
                    {result.approval_details?.reasoning || "AI analyzed 30-day sales velocity and recommends these placement changes."}
                  </div>
                  <div className="space-y-2">
                    {(result.approval_details?.suggestions || []).map((s, si) => {
                      const prioColors = { high: 'border-[rgba(255,180,171,0.35)] bg-[rgba(147,0,10,0.18)]', medium: 'border-[rgba(233,226,213,0.3)] bg-[rgba(74,70,61,0.4)]', low: 'border-[rgba(67,72,72,0.22)] bg-[var(--surface-low)]' };
                      const prioText = { high: 'text-[#ffb4ab]', medium: 'text-[#e9e2d5]', low: 'text-[#8d9192]' };
                      return (
                        <div key={si} className={`rounded-md border p-3 ${prioColors[s.priority] || prioColors.low}`}>
                          <div className="flex items-center gap-2">
                            <MoveRight size={12} className="text-[#8bd3d4]" />
                            <span className="text-sm font-bold text-[var(--text)]">{s.product_name}</span>
                            <span className={`ml-auto rounded-sm px-2 py-0.5 text-[9px] font-bold uppercase ${prioText[s.priority] || ''}`}>
                              {s.priority}
                            </span>
                          </div>
                          <div className="mt-1 flex items-center gap-1.5 text-xs text-[#8d9192]">
                            <span>{s.from_zone}</span>
                            <ArrowRight size={10} />
                            <span className="font-semibold text-[#8bd3d4]">{s.to_zone}</span>
                            {s.suggested_shelf_level && (
                              <span className="ml-2 rounded-sm bg-[rgba(139,211,212,0.14)] px-1.5 py-0.5 text-[8px] font-bold text-[#8bd3d4]">
                                {s.suggested_shelf_level === 'eye_level' ? 'Eye Level' : s.suggested_shelf_level}
                              </span>
                            )}
                          </div>
                          <p className="mt-1 text-[11px] leading-snug text-[var(--text-muted)]">{s.reason}</p>
                        </div>
                      );
                    })}
                  </div>
                  {result.approval_details?.velocity_summary && (
                    <div className="grid grid-cols-3 gap-2">
                      <div className="rounded-sm border border-[rgba(67,72,72,0.22)] bg-[var(--surface-low)] p-2.5 text-center shadow-sm">
                        <span className="text-[9px] font-black uppercase tracking-tighter leading-none text-[#8d9192]">Fast</span>
                        <div className="mt-0.5 text-[12px] font-black leading-none text-[#8bd3d4]">{result.approval_details.velocity_summary.fast_movers}</div>
                      </div>
                      <div className="rounded-sm border border-[rgba(67,72,72,0.22)] bg-[var(--surface-low)] p-2.5 text-center shadow-sm">
                        <span className="text-[9px] font-black uppercase tracking-tighter leading-none text-[#8d9192]">Moderate</span>
                        <div className="mt-0.5 text-[12px] font-black leading-none text-[#e9e2d5]">{result.approval_details.velocity_summary.moderate}</div>
                      </div>
                      <div className="rounded-sm border border-[rgba(67,72,72,0.22)] bg-[var(--surface-low)] p-2.5 text-center shadow-sm">
                        <span className="text-[9px] font-black uppercase tracking-tighter leading-none text-[#8d9192]">Slow</span>
                        <div className="mt-0.5 text-[12px] font-black leading-none text-[#ffb4ab]">{result.approval_details.velocity_summary.slow_movers}</div>
                      </div>
                    </div>
                  )}
                </div>
              ) : isInventory ? (
                <div className="flex-1 space-y-4 border-b border-[rgba(67,72,72,0.18)] p-5">
                  <div className="flex items-center gap-2 text-[#e9e2d5]">
                    <AlertTriangle size={16} />
                    <span className="atelier-label text-[10px]">Restock Needed</span>
                  </div>
                  <div className="text-sm font-medium leading-relaxed text-[var(--text-muted)]">
                    Stock limit breached. Would you like to launch the autonomous agents to restock this?
                  </div>
                  <div className="rounded-sm border border-[rgba(67,72,72,0.22)] bg-[var(--surface-low)] p-3 text-xs italic text-[var(--text-muted)] shadow-sm">
                    <span className="mr-1 font-bold not-italic text-[#8bd3d4]">Action:</span>
                    {result.approval_details?.action_plan || "Trigger autonomous procurement flow to find the best supplier."}
                  </div>
                </div>
              ) : (
                <div className="flex-1">
                  <div className="p-5 grid grid-cols-2 gap-4 relative">
                    <div className="absolute left-1/2 top-1/2 z-10 flex h-8 w-8 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-sm border border-[rgba(67,72,72,0.22)] bg-[var(--surface-low)]">
                      <ArrowRight size={14} className="text-[#8d9192]" />
                    </div>

                    <div className="space-y-1">
                      <div className="atelier-label text-[10px] text-[#8d9192]">Usual Price</div>
                      <div className="text-xl font-black text-[#8d9192] line-through">₹195</div>
                      <div className="text-[10px] font-bold text-[#8d9192]">From MegaMart</div>
                    </div>

                    <div className="space-y-1 text-right">
                      <div className="mb-1 atelier-label text-[10px] leading-none text-[#8bd3d4]">New Best Price</div>
                      <div className="mb-1 text-2xl font-black leading-none tracking-tight text-[#8bd3d4]">₹{topSupplier.price_per_unit || '---'}</div>
                      <div className="text-[10px] font-bold text-[#8bd3d4]/70">You save ₹2,500!</div>
                    </div>
                  </div>

                  <div className="px-5 pb-5 grid grid-cols-3 gap-2">
                    <div className="flex flex-col items-center justify-center rounded-sm border border-[rgba(67,72,72,0.22)] bg-[var(--surface-low)] p-2.5 text-center shadow-sm">
                      <ShieldCheck size={14} className="mb-1 text-[#8bd3d4]" />
                      <span className="text-[9px] font-black uppercase tracking-tighter leading-none text-[#8d9192]">Trust</span>
                      <span className="mt-0.5 text-[12px] font-black leading-none text-[var(--text)]">94%</span>
                    </div>
                    <div className="flex flex-col items-center justify-center rounded-sm border border-[rgba(67,72,72,0.22)] bg-[var(--surface-low)] p-2.5 text-center shadow-sm">
                      <Clock size={14} className="mb-1 text-[#e9e2d5]" />
                      <span className="text-[9px] font-black uppercase tracking-tighter leading-none text-[#8d9192]">Wait</span>
                      <span className="mt-0.5 text-[12px] font-black leading-none text-[var(--text)]">1 Day</span>
                    </div>
                    <div className="flex flex-col items-center justify-center rounded-sm border border-[rgba(67,72,72,0.22)] bg-[var(--surface-low)] p-2.5 text-center shadow-sm">
                      <TrendingUp size={14} className="mb-1 text-[#8bd3d4]" />
                      <span className="text-[9px] font-black uppercase tracking-tighter leading-none text-[#8d9192]">Quality</span>
                      <span className="mt-0.5 text-[12px] font-black leading-none text-[var(--text)]">AA+</span>
                    </div>
                  </div>
                </div>
              )}

              {negId && (
                <div className="border-t border-[rgba(67,72,72,0.18)]">
                  <button 
                    onClick={() => toggleThread(approval.id)}
                    className="group flex w-full items-center justify-between p-4 text-[#8d9192] transition-colors hover:text-[var(--text)]"
                  >
                    <div className="flex items-center gap-2">
                      <MessageCircle size={16} />
                      <span className="atelier-label text-[10px]">See our WhatsApp talk</span>
                    </div>
                    {expandedThreads[approval.id] ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </button>
                  
                  <AnimatePresence>
                    {expandedThreads[approval.id] && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="overflow-hidden bg-[rgba(12,15,14,0.35)] px-4 pb-4"
                      >
                        <div className="pt-2 flex flex-col gap-3">
                          {thread.map((msg, mid) => (
                            <div key={mid} className={`flex flex-col ${msg.direction === 'outbound' ? 'items-end' : 'items-start'}`}>
                              <div className="mb-1 text-[8px] font-black uppercase tracking-widest text-[#8d9192]">
                                {msg.direction === 'outbound' ? 'RetailOS sent:' : 'Supplier replied:'}
                              </div>
                              <div className={msg.direction === 'outbound' ? 'whatsapp-bubble-out text-[13px] leading-snug' : 'whatsapp-bubble-in text-[13px] leading-snug'}>
                                {msg.message}
                              </div>
                              <div className="mt-1 text-[9px] font-medium text-[#8d9192]">
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

              <div className="flex flex-col gap-2 bg-[rgba(12,15,14,0.35)] p-4 lg:flex-row">
                <motion.button
                  whileTap={{ scale: 0.98 }}
                  onClick={() => handleAction(approval.id, 'approve')}
                  className="btn-success w-full flex items-center justify-center gap-2"
                >
                  <Check size={20} strokeWidth={3} />
                  <span>{isShelfOpt ? 'APPLY CHANGES' : 'YES, ORDER IT'}</span>
                </motion.button>
                <motion.button
                  whileTap={{ scale: 0.98 }}
                  onClick={() => handleAction(approval.id, 'reject')}
                  className="rounded-sm p-3 text-xs font-black uppercase tracking-widest text-[#ffb4ab] transition-all hover:bg-[rgba(147,0,10,0.18)] lg:w-auto"
                >
                  {isShelfOpt ? '❌ Dismiss' : '❌ No, skip'}
                </motion.button>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
