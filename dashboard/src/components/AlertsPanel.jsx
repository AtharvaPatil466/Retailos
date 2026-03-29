import React, { useState, useEffect } from 'react';
import { X, Bell, Package, TrendingUp, RotateCw, Megaphone, AlertTriangle, ChevronRight, CheckCircle2, Trash2 } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';

const SKILL_ICONS = {
  inventory: Package,
  procurement: TrendingUp,
  negotiation: RotateCw,
  customer: Megaphone,
  orchestrator: Bell,
};

const SKILL_TAB_MAP = {
  inventory: 'inventory',
  procurement: 'approvals',
  negotiation: 'approvals',
  customer: 'agents',
  orchestrator: 'home',
};

export default function AlertsPanel({ open, onClose, onNavigate, onAlertCountChange }) {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [readIds, setReadIds] = useState(() => {
    try { return JSON.parse(localStorage.getItem('read_alerts') || '[]'); } catch { return []; }
  });

  const fetchAlerts = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/alerts?limit=30');
      const data = await res.json();
      setAlerts(data || []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  };

  useEffect(() => {
    if (open) fetchAlerts();
  }, [open]);

  useEffect(() => {
    const unread = alerts.filter((a) => !readIds.includes(a.id));
    if (onAlertCountChange) onAlertCountChange(unread.length);
  }, [alerts, readIds]);

  const markRead = (id) => {
    const next = [...new Set([...readIds, id])];
    setReadIds(next);
    localStorage.setItem('read_alerts', JSON.stringify(next));
  };

  const clearAll = () => {
    const allIds = alerts.map((a) => a.id);
    const next = [...new Set([...readIds, ...allIds])];
    setReadIds(next);
    localStorage.setItem('read_alerts', JSON.stringify(next));
  };

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-50 bg-black/20 backdrop-blur-sm"
          />
          <motion.aside
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 25, stiffness: 250 }}
            className="fixed right-0 top-0 z-50 flex h-full w-full max-w-md flex-col border-l border-black/5 bg-[rgba(244,239,230,0.98)] shadow-2xl"
          >
            <div className="flex items-center justify-between border-b border-black/5 px-6 py-5">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-red-100 text-red-600">
                  <Bell size={18} />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-stone-900">Alerts</h2>
                  <p className="text-xs text-stone-500">{alerts.filter((a) => !readIds.includes(a.id)).length} unread</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={clearAll} className="rounded-lg px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest text-stone-500 hover:bg-stone-200">
                  Clear all
                </button>
                <button onClick={onClose} className="rounded-full border border-black/10 bg-white/80 p-2 text-stone-500 hover:text-stone-900">
                  <X size={16} />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4">
              {loading && alerts.length === 0 && (
                <div className="py-12 text-center text-sm text-stone-400">Loading alerts...</div>
              )}
              {!loading && alerts.length === 0 && (
                <div className="py-12 text-center">
                  <CheckCircle2 size={32} className="mx-auto mb-3 text-emerald-400" />
                  <p className="text-sm font-semibold text-stone-600">All clear!</p>
                  <p className="mt-1 text-xs text-stone-400">No critical alerts in the last 48 hours.</p>
                </div>
              )}

              <div className="space-y-2">
                {alerts.map((alert) => {
                  const isRead = readIds.includes(alert.id);
                  const Icon = SKILL_ICONS[alert.skill] || AlertTriangle;
                  const targetTab = SKILL_TAB_MAP[alert.skill] || 'home';

                  return (
                    <div
                      key={alert.id}
                      onClick={() => markRead(alert.id)}
                      className={`group cursor-pointer rounded-[20px] border p-4 transition-all ${
                        isRead
                          ? 'border-black/5 bg-white/40 opacity-60'
                          : 'border-amber-200 bg-white/80 shadow-sm'
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <div className={`mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl ${
                          isRead ? 'bg-stone-100 text-stone-400' : 'bg-amber-100 text-amber-700'
                        }`}>
                          <Icon size={14} />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="text-sm font-semibold text-stone-900 leading-snug">
                            {alert.decision}
                          </div>
                          <div className="mt-1 flex items-center gap-2 text-[10px]">
                            <span className="font-bold uppercase tracking-wider text-stone-500">
                              {alert.skill}
                            </span>
                            <span className="text-stone-300">&middot;</span>
                            <span className="text-stone-400">
                              {alert.timestamp ? new Date(alert.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
                            </span>
                          </div>
                        </div>
                        <button
                          onClick={(e) => { e.stopPropagation(); onNavigate(targetTab); }}
                          className="flex-shrink-0 rounded-lg p-1.5 text-stone-400 opacity-0 transition-all hover:bg-stone-100 hover:text-stone-700 group-hover:opacity-100"
                          title={`Go to ${targetTab}`}
                        >
                          <ChevronRight size={14} />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
