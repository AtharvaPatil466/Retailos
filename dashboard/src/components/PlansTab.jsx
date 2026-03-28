import React from 'react';
import { motion } from 'framer-motion';
import { CheckCircle2, CircleDashed, FolderKanban, Layers3, Sparkles } from 'lucide-react';

const STATUS_STYLES = {
  in_progress: {
    label: 'In Progress',
    color: 'text-teal-700',
    chip: 'bg-teal-50 border-teal-200',
  },
  planned: {
    label: 'Planned',
    color: 'text-amber-700',
    chip: 'bg-amber-50 border-amber-200',
  },
  done: {
    label: 'Done',
    color: 'text-emerald-700',
    chip: 'bg-emerald-50 border-emerald-200',
  },
};

export default function PlansTab({ plans }) {
  return (
    <div className="space-y-6 lg:space-y-8">
      <div className="overflow-hidden rounded-[2rem] border border-black/5 bg-[linear-gradient(135deg,rgba(239,247,242,0.96),rgba(247,241,232,0.9))] shadow-[0_20px_55px_rgba(0,0,0,0.06)]">
        <div className="p-6 lg:p-8">
          <div className="inline-flex items-center gap-2 rounded-full border border-teal-200 bg-white/75 px-3 py-1 text-[10px] font-black uppercase tracking-[0.24em] text-teal-700">
            <FolderKanban size={12} />
            Execution Map
          </div>
          <h2 className="font-display mt-4 text-2xl font-bold tracking-tight text-stone-900 lg:text-4xl">Two plans, one product direction</h2>
          <p className="mt-3 max-w-3xl text-sm leading-relaxed text-stone-600 lg:text-base">
            We are improving the dashboard experience and building a custom work setup around the user at the same time, so the UI looks better and works more personally.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 2xl:grid-cols-2 gap-4 lg:gap-6">
        {plans.map((plan, index) => {
          const status = STATUS_STYLES[plan.status] || STATUS_STYLES.planned;

          return (
            <motion.div
              key={plan.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.08 }}
              className="overflow-hidden rounded-[2rem] border border-black/5 bg-[rgba(255,252,247,0.86)] text-stone-900 shadow-[0_20px_55px_rgba(0,0,0,0.06)]"
            >
              <div className="border-b border-black/5 p-6 lg:p-7">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className={`inline-flex items-center gap-2 px-3 py-1 rounded-full border text-[10px] font-black uppercase tracking-[0.18em] ${status.chip} ${status.color}`}>
                      <Layers3 size={12} />
                      {status.label}
                    </div>
                    <h3 className="font-display mt-4 text-xl font-bold tracking-tight text-stone-900 lg:text-2xl">{plan.title}</h3>
                    <p className="mt-1 text-sm text-stone-500">Owner: {plan.owner}</p>
                  </div>
                  <div className="text-right">
                    <div className="text-3xl font-black text-stone-900">{plan.progress}%</div>
                    <div className="text-[10px] font-black uppercase tracking-widest text-stone-500">complete</div>
                  </div>
                </div>

                <div className="mt-5 h-2 w-full overflow-hidden rounded-full bg-stone-200">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-teal-700 via-teal-600 to-amber-600"
                    style={{ width: `${plan.progress}%` }}
                  />
                </div>
              </div>

              <div className="p-6 lg:p-7 space-y-5">
                <div>
                  <div className="text-[10px] font-black uppercase tracking-[0.2em] text-stone-500">Summary</div>
                  <p className="mt-2 text-sm leading-relaxed text-stone-700">{plan.summary}</p>
                </div>

                <div>
                  <div className="text-[10px] font-black uppercase tracking-[0.2em] text-stone-500">Current Focus</div>
                  <p className="mt-2 text-sm leading-relaxed text-stone-700">{plan.focus}</p>
                </div>

                <div>
                  <div className="text-[10px] font-black uppercase tracking-[0.2em] text-stone-500">Milestones</div>
                  <div className="space-y-3 mt-3">
                    {plan.milestones.map((milestone) => (
                      <div key={milestone.label} className="flex items-center gap-3 text-sm">
                        {milestone.done ? (
                          <CheckCircle2 size={16} className="text-emerald-700 flex-shrink-0" />
                        ) : (
                          <CircleDashed size={16} className="text-stone-400 flex-shrink-0" />
                        )}
                        <span className={milestone.done ? 'text-stone-800' : 'text-stone-500'}>
                          {milestone.label}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-2xl border border-black/5 bg-white/88 p-4 shadow-sm">
                  <div className="flex items-center gap-2 text-teal-700">
                    <Sparkles size={14} />
                    <span className="text-[10px] font-black uppercase tracking-[0.18em]">Next Step</span>
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-stone-700">{plan.nextAction}</p>
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
