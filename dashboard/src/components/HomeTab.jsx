import React from 'react';
import { motion } from 'framer-motion';
import { 
  TrendingUp, 
  Package, 
  Megaphone, 
  Clock,
  ChevronRight,
  CheckCircle2,
  AlertCircle,
  RotateCw,
  Zap,
  ArrowUpRight,
  Briefcase,
  FolderKanban,
  UserCircle2
} from 'lucide-react';

const PRODUCT_ICONS = {
  'SKU-001': '🍦', // Ice Cream
  'SKU-002': '🧂', // Salt
  'SKU-003': '🍼', // Milk
  'SKU-004': '🍞', // Bread
  'SKU-005': '🥚', // Eggs
};

export default function HomeTab({
  stats,
  logs,
  approvalCount,
  plans,
  workspaceProfile,
  onGoToApprovals,
  onGoToPlans,
  onGoToWorkspace,
}) {
  const getEventIcon = (log) => {
    if (log.skill === 'inventory') return <Package size={14} className="text-amber-400" />;
    if (log.skill === 'procurement') return <TrendingUp size={14} className="text-blue-400" />;
    if (log.skill === 'negotiation') return <RotateCw size={14} className="text-green-400" />;
    if (log.skill === 'customer') return <Megaphone size={14} className="text-purple-400" />;
    return <CheckCircle2 size={14} className="text-white/40" />;
  };

  const getLogMessage = (log) => {
    if (log.skill === 'inventory' && log.event_type === 'low_stock_detected') {
      try {
        const data = JSON.parse(log.outcome);
        const icon = PRODUCT_ICONS[data.sku] || '📦';
        return `${icon} ${data.product_name} was running low. Checking with suppliers...`;
      } catch { return log.decision; }
    }
    if (log.skill === 'negotiation' && log.event_type === 'outreach_sent') {
      const meta = log.metadata || {};
      return `🤝 Sent a message to ${meta.supplier_id || 'supplier'} to get a better price.`;
    }
    if (log.skill === 'negotiation' && log.event_type === 'reply_parsed') {
      return `💬 Supplier replied! They offered a good deal. Waiting for your approval.`;
    }
    if (log.skill === 'customer' && log.event_type === 'offer_sent') {
      return `📣 Sent a special offer to customers. 12 people already looked at it!`;
    }
    if (log.skill === 'orchestrator' && log.event_type === 'owner_approved') {
      return `✅ You approved the order. I've placed it with the supplier.`;
    }
    return log.decision;
  };

  const getStatusColor = (log) => {
    if (log.status === 'alert' || log.status === 'pending') return 'bg-amber-400';
    if (log.status === 'error' || log.status === 'failed') return 'bg-red-500';
    if (log.status === 'success' || log.status === 'approved') return 'bg-green-500';
    return 'bg-blue-500';
  };

  const statCards = [
    { label: 'Money Saved', value: `₹${stats.moneySaved.toLocaleString()}`, icon: TrendingUp, color: 'text-emerald-700', bg: 'bg-emerald-100' },
    { label: 'Orders Placed', value: stats.ordersPlaced, icon: Package, color: 'text-teal-700', bg: 'bg-teal-100' },
    { label: 'Offers Sent', value: stats.offersSent, icon: Megaphone, color: 'text-amber-700', bg: 'bg-amber-100' },
    { label: 'Hours Saved', value: `${stats.hoursSaved} hrs`, icon: Clock, color: 'text-stone-800', bg: 'bg-stone-200' },
  ];

  return (
    <div className="space-y-8 lg:space-y-10">
      <section className="grid gap-5 xl:grid-cols-[1.35fr_0.65fr]">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="overflow-hidden rounded-[32px] border border-black/5 bg-[linear-gradient(135deg,rgba(255,252,247,0.95),rgba(233,227,216,0.85))] p-7 shadow-[0_28px_70px_rgba(0,0,0,0.08)] lg:p-9"
        >
          <div className="inline-flex items-center gap-2 rounded-full border border-black/5 bg-white/70 px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] text-stone-600">
            Retail operations overview
          </div>
          <h1 className="font-display mt-5 max-w-3xl text-4xl font-bold tracking-tight text-stone-900 lg:text-6xl">
            A cleaner control room for what your store needs next.
          </h1>
          <p className="mt-5 max-w-2xl text-base leading-relaxed text-stone-600 lg:text-lg">
            Keep the experience web-first: clearer decisions, sharper visibility, and a workspace that feels built for an owner running a real store instead of a generic AI dashboard.
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-3">
            <button
              onClick={onGoToApprovals}
              className={`inline-flex items-center gap-2 rounded-full px-5 py-3 text-sm font-bold transition-all ${
                approvalCount > 0
                  ? 'bg-stone-900 text-white hover:bg-black'
                  : 'bg-emerald-700 text-white hover:bg-emerald-600'
              }`}
            >
              {approvalCount > 0 ? <AlertCircle size={16} /> : <CheckCircle2 size={16} />}
              <span>
                {approvalCount > 0 ? `Review ${approvalCount} pending approvals` : 'Everything is stable right now'}
              </span>
              <ChevronRight size={16} />
            </button>
            <button
              onClick={onGoToPlans}
              className="inline-flex items-center gap-2 rounded-full border border-black/10 bg-white/70 px-5 py-3 text-sm font-bold text-stone-700 transition-all hover:bg-white"
            >
              <FolderKanban size={16} />
              <span>See project plans</span>
            </button>
          </div>
        </motion.div>

        <motion.button
          onClick={onGoToWorkspace}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.06 }}
          className="rounded-[32px] border border-black/5 bg-[rgba(255,252,247,0.78)] p-7 text-left shadow-[0_24px_60px_rgba(0,0,0,0.06)] transition-all hover:bg-white/90"
        >
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-100 text-emerald-700">
                <UserCircle2 size={24} />
              </div>
              <div>
                <div className="text-[10px] font-black uppercase tracking-[0.22em] text-stone-500">Workspace profile</div>
                <h3 className="font-display mt-1 text-2xl font-bold tracking-tight text-stone-900">
                  {workspaceProfile.name}
                </h3>
              </div>
            </div>
            <Briefcase size={18} className="text-stone-400" />
          </div>
          <p className="mt-5 text-sm leading-relaxed text-stone-600">
            {workspaceProfile.workStyle}
          </p>
          <div className="mt-6 space-y-3">
            {workspaceProfile.preferences.slice(0, 3).map((item) => (
              <div key={item.label} className="flex items-start justify-between gap-4 border-t border-black/5 pt-3 text-sm">
                <span className="text-stone-500">{item.label}</span>
                <span className="max-w-[60%] text-right font-semibold text-stone-800">{item.value}</span>
              </div>
            ))}
          </div>
        </motion.button>
      </section>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {statCards.map((stat, i) => (
          <motion.div
            key={stat.label}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.08 }}
            className="rounded-[28px] border border-black/5 bg-[rgba(255,252,247,0.72)] p-5 shadow-[0_18px_45px_rgba(0,0,0,0.05)] transition-all"
          >
            <div className={`mb-4 flex h-11 w-11 items-center justify-center rounded-2xl ${stat.bg}`}>
              <stat.icon size={18} className={stat.color} />
            </div>
            <div className="text-[11px] font-bold uppercase tracking-[0.18em] text-stone-500">{stat.label}</div>
            <div className={`mt-1 text-2xl font-black tracking-tight ${stat.color}`}>{stat.value}</div>
          </motion.div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[1.15fr_0.85fr]">
        <motion.button
          onClick={onGoToPlans}
          whileTap={{ scale: 0.99 }}
          className="rounded-[32px] border border-black/5 bg-[rgba(255,252,247,0.78)] p-6 text-left shadow-[0_22px_55px_rgba(0,0,0,0.06)] transition-all hover:bg-white/90 lg:p-7"
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-black/5 bg-teal-50 px-3 py-1 text-[10px] font-black uppercase tracking-[0.2em] text-teal-700">
                <FolderKanban size={12} />
                Two Plans In Motion
              </div>
              <h3 className="font-display mt-4 text-2xl font-bold tracking-tight text-stone-900">Build the product in two tracks</h3>
              <p className="mt-2 max-w-2xl text-sm leading-relaxed text-stone-600">
                One plan sharpens the UI. The other shapes a custom work setup around the user so RetailOS fits real daily flow.
              </p>
            </div>
            <ArrowUpRight size={18} className="flex-shrink-0 text-teal-700" />
          </div>

          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            {plans.map((plan) => (
              <div key={plan.id} className="rounded-[26px] border border-black/5 bg-[linear-gradient(180deg,rgba(255,255,255,0.7),rgba(246,241,233,0.9))] p-5">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-black text-stone-900">{plan.title}</div>
                  <div className="text-[10px] font-black uppercase tracking-widest text-stone-500">
                    {plan.progress}%
                  </div>
                </div>
                <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-stone-200">
                  <div className="h-full rounded-full bg-gradient-to-r from-teal-700 to-amber-700" style={{ width: `${plan.progress}%` }} />
                </div>
                <p className="mt-3 text-xs leading-relaxed text-stone-600">{plan.focus}</p>
              </div>
            ))}
          </div>
        </motion.button>

        <div className="rounded-[32px] border border-black/5 bg-stone-900 p-6 text-stone-50 shadow-[0_22px_55px_rgba(0,0,0,0.18)] lg:p-7">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/10 text-amber-300">
                <Zap size={20} />
              </div>
              <div>
                <div className="text-[10px] font-black uppercase tracking-[0.2em] text-stone-400">Live pulse</div>
                <h3 className="font-display mt-1 text-2xl font-bold">What matters right now</h3>
              </div>
            </div>
          </div>
          <div className="mt-6 space-y-4">
            <div className="rounded-[24px] bg-white/5 p-4">
              <div className="text-[10px] font-black uppercase tracking-[0.18em] text-stone-400">Approvals</div>
              <div className="mt-2 text-4xl font-black text-white">{approvalCount}</div>
              <p className="mt-2 text-sm leading-relaxed text-stone-300">
                Decisions that still need the owner before the system can commit to a supplier or next action.
              </p>
            </div>
            <div className="rounded-[24px] bg-white/5 p-4">
              <div className="text-[10px] font-black uppercase tracking-[0.18em] text-stone-400">Workspace intent</div>
              <p className="mt-2 text-sm leading-relaxed text-stone-200">
                Keep the page calm, web-first, and practical: clear summaries, strong typography, and less AI-dashboard noise.
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="space-y-4">
        <div className="flex items-center justify-between px-1">
          <h2 className="text-xs font-black uppercase tracking-[0.22em] text-stone-500">What&apos;s happening right now</h2>
          <div className="hidden lg:flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.2em] text-stone-400">
            <Zap size={10} className="text-amber-700" />
            <span>Live Feed</span>
          </div>
        </div>
        <div className="space-y-3">
          {logs.slice(0, 20).map((log, i) => (
            <motion.div
              key={log.id}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.03 }}
              className="group flex items-start gap-4 rounded-[24px] border border-black/5 bg-[rgba(255,252,247,0.74)] p-4 transition-all hover:bg-white/90"
            >
              <div className="relative mt-1.5 flex-shrink-0">
                <div className={`w-2 h-2 rounded-full ${getStatusColor(log)}`} />
                <div className={`absolute inset-0 w-2 h-2 rounded-full ${getStatusColor(log)} animate-ping opacity-20`} />
              </div>
              <div className="flex-1 min-w-0 space-y-1">
                <div className="text-sm font-medium leading-snug text-stone-900">
                  {getLogMessage(log)}
                </div>
                <div className="flex items-center gap-2">
                  <div className="text-[10px] font-bold uppercase tracking-wider text-stone-500">
                    {new Date(log.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </div>
                  <span className="text-[8px] text-stone-300">•</span>
                  <div className="flex items-center gap-1">
                    {getEventIcon(log)}
                    <span className="text-[10px] font-bold uppercase tracking-tighter text-stone-500">
                      {log.skill === 'orchestrator' ? 'Manager' : log.skill}
                    </span>
                  </div>
                </div>
              </div>
              <div className="hidden transition-opacity group-hover:opacity-100 lg:block">
                <ArrowUpRight size={14} className="text-stone-400" />
              </div>
            </motion.div>
          ))}
          {logs.length === 0 && (
            <div className="rounded-[28px] border-2 border-dashed border-black/10 py-20 text-center font-bold uppercase tracking-[0.22em] text-stone-400">
              Waiting for actions...
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
