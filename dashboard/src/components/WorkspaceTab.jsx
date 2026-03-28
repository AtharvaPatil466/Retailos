import React from 'react';
import { motion } from 'framer-motion';
import { Briefcase, CheckCircle2, Clock3, MapPin, Sparkles, Target, UserCircle2 } from 'lucide-react';

export default function WorkspaceTab({ plans, workspaceProfile }) {
  return (
    <div className="space-y-6 lg:space-y-8">
      <div className="grid grid-cols-1 xl:grid-cols-[1.15fr_0.85fr] gap-4 lg:gap-6">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-[2rem] border border-black/5 bg-[linear-gradient(135deg,rgba(239,247,242,0.96),rgba(229,240,238,0.88))] p-6 text-stone-900 shadow-[0_20px_55px_rgba(0,0,0,0.06)] lg:p-8"
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-white/70 px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] text-emerald-700">
                <Briefcase size={12} />
                User Workspace
              </div>
              <h2 className="font-display mt-4 text-2xl font-bold tracking-tight lg:text-4xl">{workspaceProfile.name}</h2>
              <p className="mt-3 max-w-2xl text-sm leading-relaxed text-stone-600 lg:text-base">{workspaceProfile.workStyle}</p>
            </div>
            <div className="flex h-14 w-14 items-center justify-center rounded-3xl border border-white/70 bg-white/75 text-emerald-700 shadow-sm">
              <UserCircle2 size={30} />
            </div>
          </div>

          <div className="grid sm:grid-cols-2 gap-3 mt-6">
            <div className="rounded-2xl border border-black/5 bg-white/80 p-4 shadow-sm">
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.18em] text-stone-500">
                <Target size={12} />
                Role
              </div>
              <div className="mt-2 text-lg font-black text-stone-900">{workspaceProfile.role}</div>
            </div>
            <div className="rounded-2xl border border-black/5 bg-white/80 p-4 shadow-sm">
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.18em] text-stone-500">
                <MapPin size={12} />
                Context
              </div>
              <div className="mt-2 text-lg font-black text-stone-900">{workspaceProfile.location}</div>
            </div>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.06 }}
          className="rounded-[2rem] border border-black/5 bg-[rgba(255,252,247,0.82)] p-6 text-stone-900 shadow-[0_20px_55px_rgba(0,0,0,0.06)] lg:p-7"
        >
          <div className="text-[10px] font-black uppercase tracking-[0.2em] text-stone-500">Plan Alignment</div>
          <div className="space-y-4 mt-4">
            {plans.map((plan) => (
              <div key={plan.id} className="rounded-2xl border border-black/5 bg-white/88 p-4 shadow-sm">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-black text-stone-900">{plan.title}</div>
                  <div className="text-xs font-bold text-stone-500">{plan.progress}%</div>
                </div>
                <p className="mt-2 text-sm leading-relaxed text-stone-600">{plan.nextAction}</p>
              </div>
            ))}
          </div>
        </motion.div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[0.9fr_1.1fr] gap-4 lg:gap-6">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.12 }}
          className="rounded-[2rem] border border-black/5 bg-[rgba(255,252,247,0.82)] p-6 text-stone-900 shadow-[0_20px_55px_rgba(0,0,0,0.06)] lg:p-7"
        >
          <div className="flex items-center gap-2 text-emerald-700">
            <Target size={16} />
            <h3 className="text-sm font-black uppercase tracking-[0.16em] text-stone-800">What matters to the user</h3>
          </div>
          <div className="space-y-3 mt-5">
            {workspaceProfile.goals.map((goal) => (
              <div key={goal} className="flex items-start gap-3">
                <CheckCircle2 size={16} className="text-emerald-700 flex-shrink-0 mt-0.5" />
                <p className="text-sm leading-relaxed text-stone-700">{goal}</p>
              </div>
            ))}
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.18 }}
          className="rounded-[2rem] border border-black/5 bg-[rgba(255,252,247,0.82)] p-6 text-stone-900 shadow-[0_20px_55px_rgba(0,0,0,0.06)] lg:p-7"
        >
          <div className="flex items-center gap-2 text-teal-700">
            <Clock3 size={16} />
            <h3 className="text-sm font-black uppercase tracking-[0.16em] text-stone-800">Daily flow setup</h3>
          </div>
          <div className="space-y-4 mt-5">
            {workspaceProfile.routines.map((routine) => (
              <div key={routine.label} className="rounded-2xl border border-black/5 bg-white/88 p-4 shadow-sm">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-black text-stone-900">{routine.label}</div>
                  <div className="text-[11px] font-black uppercase tracking-widest text-teal-700">{routine.time}</div>
                </div>
                <p className="mt-2 text-sm leading-relaxed text-stone-600">{routine.detail}</p>
              </div>
            ))}
          </div>
        </motion.div>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.24 }}
        className="rounded-[2rem] border border-black/5 bg-[rgba(255,252,247,0.82)] p-6 text-stone-900 shadow-[0_20px_55px_rgba(0,0,0,0.06)] lg:p-7"
      >
        <div className="flex items-center gap-2 text-amber-700">
          <Sparkles size={16} />
          <h3 className="text-sm font-black uppercase tracking-[0.16em] text-stone-800">Preference layer</h3>
        </div>
        <div className="grid md:grid-cols-2 xl:grid-cols-4 gap-3 mt-5">
          {workspaceProfile.preferences.map((item) => (
            <div key={item.label} className="rounded-2xl border border-black/5 bg-white/88 p-4 shadow-sm">
              <div className="text-[10px] font-black uppercase tracking-[0.18em] text-stone-500">{item.label}</div>
              <div className="mt-2 text-sm font-semibold leading-relaxed text-stone-800">{item.value}</div>
            </div>
          ))}
        </div>
      </motion.div>
    </div>
  );
}
