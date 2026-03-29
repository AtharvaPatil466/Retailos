import React, { useState, useEffect } from 'react';
import { Truck, Search, Plus, ChevronDown, ChevronUp, X, Star, Clock, Package, AlertTriangle } from 'lucide-react';
import { motion } from 'framer-motion';

function TrustBar({ score }) {
  const color = score >= 80 ? 'bg-emerald-500' : score >= 60 ? 'bg-amber-500' : 'bg-red-500';
  const textColor = score >= 80 ? 'text-emerald-700' : score >= 60 ? 'text-amber-700' : 'text-red-700';
  return (
    <div className="flex items-center gap-3">
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-stone-200">
        <div className={`h-full rounded-full ${color} transition-all`} style={{ width: `${score}%` }} />
      </div>
      <span className={`text-sm font-black ${textColor}`}>{score}</span>
    </div>
  );
}

function SupplierCard({ supplier, onViewHistory }) {
  const [expanded, setExpanded] = useState(false);
  const [history, setHistory] = useState(null);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const handleToggle = async () => {
    if (!expanded && !history) {
      setLoadingHistory(true);
      try {
        const res = await fetch(`/api/suppliers/${supplier.supplier_id}/history`);
        const data = await res.json();
        setHistory(data);
      } catch (err) {
        console.error(err);
      } finally {
        setLoadingHistory(false);
      }
    }
    setExpanded(!expanded);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="overflow-hidden rounded-[28px] border border-black/5 bg-[rgba(255,252,247,0.9)] shadow-[0_18px_45px_rgba(0,0,0,0.05)] transition-colors hover:bg-white"
    >
      <div className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.18em] text-stone-500">{supplier.supplier_id}</div>
            <h3 className="mt-1 text-lg font-bold text-stone-900">{supplier.supplier_name}</h3>
            <div className="mt-1 text-xs text-stone-500">{supplier.contact_phone}</div>
          </div>
          <div className="flex flex-col items-end gap-1">
            <span className="rounded-full bg-stone-100 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-stone-600">
              {supplier.location}
            </span>
          </div>
        </div>

        <div className="mt-4">
          <div className="mb-1 text-[10px] font-black uppercase tracking-wider text-stone-500">Trust Score</div>
          <TrustBar score={supplier.trust_score} />
        </div>

        <div className="mt-4 grid grid-cols-3 gap-3">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-stone-500">Delivery</div>
            <div className="mt-1 flex items-center gap-1 text-sm font-bold text-stone-900">
              <Clock size={12} className="text-stone-400" />
              {supplier.delivery_days}d
            </div>
          </div>
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-stone-500">Min Order</div>
            <div className="mt-1 text-sm font-bold text-stone-900">{supplier.min_order_qty} units</div>
          </div>
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-stone-500">Price/Unit</div>
            <div className="mt-1 text-sm font-bold text-stone-900">Rs {supplier.price_per_unit}</div>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-1.5">
          {(supplier.categories || []).slice(0, 4).map((cat) => (
            <span key={cat} className="rounded-full bg-teal-50 px-2 py-0.5 text-[10px] font-bold text-teal-700">
              {cat}
            </span>
          ))}
        </div>

        <div className="mt-3 text-xs text-stone-500">
          <span className="font-semibold">Terms:</span> {supplier.payment_terms}
        </div>

        <button
          onClick={handleToggle}
          className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl border border-black/5 bg-stone-50 py-2 text-xs font-bold text-stone-600 transition-colors hover:bg-stone-100"
        >
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          {expanded ? 'Hide History' : 'View History'}
        </button>

        {expanded && (
          <div className="mt-3 space-y-2">
            {loadingHistory && <div className="py-4 text-center text-xs text-stone-400">Loading...</div>}
            {history && history.decisions?.length > 0 ? (
              history.decisions.slice(0, 10).map((d, i) => (
                <div key={i} className="flex items-center justify-between rounded-xl bg-stone-50 px-3 py-2 text-xs">
                  <span className={`font-bold ${d.status === 'approved' ? 'text-emerald-700' : 'text-red-600'}`}>
                    {d.status}
                  </span>
                  <span className="font-semibold text-stone-700">Rs {d.amount?.toFixed(0)}</span>
                  <span className="text-stone-500">{new Date(d.timestamp * 1000).toLocaleDateString()}</span>
                </div>
              ))
            ) : (
              !loadingHistory && <div className="py-3 text-center text-xs text-stone-400">No decision history yet</div>
            )}
            {history?.trust?.breakdown && (
              <div className="rounded-xl bg-stone-50 p-3">
                <div className="mb-2 text-[10px] font-black uppercase tracking-wider text-stone-500">Trust Breakdown</div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  {Object.entries(history.trust.breakdown).map(([k, v]) => (
                    <div key={k} className="flex justify-between">
                      <span className="capitalize text-stone-600">{k.replace('_', ' ')}</span>
                      <span className="font-bold text-stone-900">{v}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </motion.div>
  );
}

function RegisterSupplierModal({ onClose, onSubmit, submitting }) {
  const [form, setForm] = useState({
    supplier_id: '',
    supplier_name: '',
    contact_phone: '',
    whatsapp_number: '',
    products: '',
    categories: '',
    price_per_unit: '',
    min_order_qty: '',
    delivery_days: '',
    payment_terms: '',
    location: '',
    notes: '',
  });

  const update = (field, value) => setForm((p) => ({ ...p, [field]: value }));

  const handleSubmit = (e) => {
    e.preventDefault();
    onSubmit({
      ...form,
      products: form.products.split(',').map((s) => s.trim()).filter(Boolean),
      categories: form.categories.split(',').map((s) => s.trim()).filter(Boolean),
      price_per_unit: Number(form.price_per_unit) || 0,
      min_order_qty: Number(form.min_order_qty) || 0,
      delivery_days: Number(form.delivery_days) || 0,
    });
  };

  const inputClass = "w-full rounded-2xl border border-black/10 bg-white/85 px-4 py-3 text-sm text-stone-900 placeholder:text-stone-400 focus:border-teal-600/50 focus:outline-none";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4 backdrop-blur-sm">
      <div className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-[28px] border border-black/5 bg-[rgba(255,252,247,0.98)] p-6 shadow-[0_30px_100px_rgba(0,0,0,0.18)] lg:p-8">
        <div className="mb-6 flex items-start justify-between">
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.22em] text-stone-500">Supplier network</div>
            <h2 className="font-display mt-2 text-3xl font-bold tracking-tight">Add Supplier</h2>
          </div>
          <button onClick={onClose} className="rounded-full border border-black/10 bg-white/80 p-2 text-stone-500 hover:text-stone-900">
            <X size={16} />
          </button>
        </div>
        <form className="space-y-4" onSubmit={handleSubmit}>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-2">
              <span className="text-xs font-black uppercase tracking-[0.18em] text-stone-500">Supplier ID</span>
              <input required value={form.supplier_id} onChange={(e) => update('supplier_id', e.target.value.toUpperCase())} className={inputClass} placeholder="SUP-021" />
            </label>
            <label className="space-y-2">
              <span className="text-xs font-black uppercase tracking-[0.18em] text-stone-500">Supplier Name</span>
              <input required value={form.supplier_name} onChange={(e) => update('supplier_name', e.target.value)} className={inputClass} placeholder="ABC Distributors" />
            </label>
            <label className="space-y-2">
              <span className="text-xs font-black uppercase tracking-[0.18em] text-stone-500">Contact Phone</span>
              <input required value={form.contact_phone} onChange={(e) => update('contact_phone', e.target.value)} className={inputClass} placeholder="+91-98xxx-xxxxx" />
            </label>
            <label className="space-y-2">
              <span className="text-xs font-black uppercase tracking-[0.18em] text-stone-500">Location</span>
              <input value={form.location} onChange={(e) => update('location', e.target.value)} className={inputClass} placeholder="Mumbai" />
            </label>
            <label className="space-y-2">
              <span className="text-xs font-black uppercase tracking-[0.18em] text-stone-500">Price per Unit (Rs)</span>
              <input type="number" min="0" value={form.price_per_unit} onChange={(e) => update('price_per_unit', e.target.value)} className={inputClass} />
            </label>
            <label className="space-y-2">
              <span className="text-xs font-black uppercase tracking-[0.18em] text-stone-500">Min Order Qty</span>
              <input type="number" min="0" value={form.min_order_qty} onChange={(e) => update('min_order_qty', e.target.value)} className={inputClass} />
            </label>
            <label className="space-y-2">
              <span className="text-xs font-black uppercase tracking-[0.18em] text-stone-500">Delivery Days</span>
              <input type="number" min="0" value={form.delivery_days} onChange={(e) => update('delivery_days', e.target.value)} className={inputClass} />
            </label>
            <label className="space-y-2">
              <span className="text-xs font-black uppercase tracking-[0.18em] text-stone-500">Payment Terms</span>
              <input value={form.payment_terms} onChange={(e) => update('payment_terms', e.target.value)} className={inputClass} placeholder="Net 30" />
            </label>
          </div>
          <label className="block space-y-2">
            <span className="text-xs font-black uppercase tracking-[0.18em] text-stone-500">Products (comma-separated)</span>
            <input value={form.products} onChange={(e) => update('products', e.target.value)} className={inputClass} placeholder="Butter, Cheese, Paneer" />
          </label>
          <label className="block space-y-2">
            <span className="text-xs font-black uppercase tracking-[0.18em] text-stone-500">Categories (comma-separated)</span>
            <input value={form.categories} onChange={(e) => update('categories', e.target.value)} className={inputClass} placeholder="Dairy, Frozen Foods" />
          </label>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="rounded-2xl px-4 py-3 text-sm font-bold text-stone-500 hover:bg-stone-100">Cancel</button>
            <button type="submit" disabled={submitting} className="rounded-2xl bg-teal-700 px-5 py-3 text-sm font-bold text-white hover:bg-teal-600 disabled:opacity-50">
              {submitting ? 'Adding...' : 'Add Supplier'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function SuppliersTab() {
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [trustFilter, setTrustFilter] = useState('All');
  const [showModal, setShowModal] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState('');

  const fetchSuppliers = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/suppliers');
      const data = await res.json();
      setSuppliers(data || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchSuppliers(); }, []);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(''), 2200);
    return () => clearTimeout(t);
  }, [toast]);

  const filtered = suppliers.filter((s) => {
    const matchesSearch = s.supplier_name?.toLowerCase().includes(searchTerm.toLowerCase()) || s.supplier_id?.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesTrust = trustFilter === 'All' || (trustFilter === 'Trusted' && s.trust_score >= 80) || (trustFilter === 'Watchlist' && s.trust_score < 60);
    return matchesSearch && matchesTrust;
  });

  const handleRegister = async (payload) => {
    setSubmitting(true);
    try {
      const res = await fetch('/api/suppliers/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error('Failed');
      setShowModal(false);
      setToast(`Added ${payload.supplier_name}`);
      await fetchSuppliers();
    } catch (err) {
      console.error(err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative max-w-md flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search suppliers..."
            className="w-full rounded-xl border border-black/10 bg-white/80 py-2.5 pl-10 pr-4 text-sm text-stone-900 placeholder:text-stone-400 focus:border-teal-600/50 focus:outline-none"
          />
        </div>
        <div className="flex items-center gap-2">
          {['All', 'Trusted', 'Watchlist'].map((f) => (
            <button
              key={f}
              onClick={() => setTrustFilter(f)}
              className={`rounded-full border px-4 py-2 text-[10px] font-black uppercase tracking-widest transition-all ${
                trustFilter === f ? 'border-teal-700 bg-teal-700 text-white' : 'border-black/10 bg-white/75 text-stone-600 hover:bg-white'
              }`}
            >
              {f === 'Trusted' ? 'Trusted (80+)' : f === 'Watchlist' ? 'Watchlist (<60)' : f}
            </button>
          ))}
          <button onClick={() => setShowModal(true)} className="flex items-center gap-2 rounded-xl bg-teal-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-teal-600">
            <Plus size={16} /> Add Supplier
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {filtered.map((s) => (
          <SupplierCard key={s.supplier_id} supplier={s} />
        ))}
        {!loading && filtered.length === 0 && (
          <div className="col-span-full rounded-[28px] border border-dashed border-black/10 bg-white/70 p-8 py-12 text-center">
            <Truck size={32} className="mx-auto mb-3 text-stone-400" />
            <h3 className="mb-1 font-semibold text-stone-800">No suppliers found</h3>
            <p className="text-sm text-stone-500">Try adjusting your search or filters</p>
          </div>
        )}
      </div>

      {showModal && (
        <RegisterSupplierModal onClose={() => setShowModal(false)} onSubmit={handleRegister} submitting={submitting} />
      )}

      {toast && (
        <div className="fixed bottom-6 right-6 z-50 rounded-2xl border border-emerald-200 bg-white px-4 py-3 text-sm font-bold text-emerald-700 shadow-[0_20px_50px_rgba(0,0,0,0.12)]">
          {toast}
        </div>
      )}
    </div>
  );
}
