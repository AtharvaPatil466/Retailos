import React, { useState, useEffect } from 'react';
import { Package, AlertTriangle, RefreshCw, PackageX, CheckCircle, Search, Plus, Minus, ImagePlus, Link2, X, ChevronDown, ChevronUp, Megaphone, TrendingDown, TrendingUp } from 'lucide-react';
import { motion } from 'framer-motion';
import { apiFetch, apiFetchArray } from '../api';

const CATEGORY_OPTIONS = ['Dairy', 'Frozen', 'Snacks', 'Beverages', 'Staples', 'Household', 'Personal Care', 'Other'];

const CATEGORY_STYLES = {
  Dairy:            { emoji: '🥛', gradient: 'from-sky-400/30 to-blue-500/20' },
  Frozen:           { emoji: '🧊', gradient: 'from-cyan-400/30 to-indigo-500/20' },
  Snacks:           { emoji: '🍪', gradient: 'from-amber-400/30 to-orange-500/20' },
  Beverages:        { emoji: '🥤', gradient: 'from-emerald-400/30 to-teal-500/20' },
  Grocery:          { emoji: '🛒', gradient: 'from-lime-400/30 to-green-500/20' },
  Cleaning:         { emoji: '🧹', gradient: 'from-violet-400/30 to-purple-500/20' },
  'Personal Care':  { emoji: '🧴', gradient: 'from-pink-400/30 to-rose-500/20' },
  'Baby Care':      { emoji: '🍼', gradient: 'from-yellow-300/30 to-amber-400/20' },
  'Protein & Health': { emoji: '💪', gradient: 'from-red-400/30 to-orange-500/20' },
  Bakery:           { emoji: '🍞', gradient: 'from-yellow-400/30 to-amber-500/20' },
  Other:            { emoji: '📦', gradient: 'from-stone-400/30 to-stone-500/20' },
};

function getCategoryPrefix(category) {
  const map = {
    Dairy: 'DAIRY',
    Frozen: 'FROZEN',
    Snacks: 'SNACKS',
    Beverages: 'BEV',
    Staples: 'STAPLE',
    Household: 'HOUSE',
    'Personal Care': 'CARE',
    Other: 'ITEM',
  };
  return map[category] || 'ITEM';
}

function getSuggestedSku(category, inventory) {
  const prefix = getCategoryPrefix(category);
  const matching = inventory
    .map((item) => item.sku)
    .filter((sku) => sku?.startsWith(`${prefix}-`))
    .map((sku) => Number.parseInt(sku.split('-').pop(), 10))
    .filter((value) => !Number.isNaN(value));

  const nextNumber = (matching.length ? Math.max(...matching) : 0) + 1;
  return `${prefix}-${String(nextNumber).padStart(3, '0')}`;
}

function ExpiryAlertsBanner() {
  const [risks, setRisks] = useState([]);
  const [expanded, setExpanded] = useState(false);
  const [dismissed, setDismissed] = useState(() => {
    try {
      const stored = JSON.parse(localStorage.getItem('expiry_dismissed') || '{}');
      const now = Date.now();
      const cleaned = {};
      for (const [k, v] of Object.entries(stored)) {
        if (now - v < 24 * 3600 * 1000) cleaned[k] = v;
      }
      return cleaned;
    } catch { return {}; }
  });

  useEffect(() => {
    apiFetchArray('/api/inventory/expiry-risks').then(setRisks);
  }, []);

  const handleDismiss = (sku) => {
    const next = { ...dismissed, [sku]: Date.now() };
    setDismissed(next);
    localStorage.setItem('expiry_dismissed', JSON.stringify(next));
  };

  const handleSendOffer = async (item) => {
    try {
      await apiFetch('/api/events', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'expiry_offer', data: { sku: item.product_id || item.sku, product_name: item.product_name } }),
      });
    } catch (err) { console.error(err); }
  };

  const visible = (Array.isArray(risks) ? risks : []).filter((r) => (r.days_to_expiry <= 5) && !dismissed[r.product_id || r.sku]);
  if (visible.length === 0) return null;

  return (
    <div className="rounded-[20px] border border-red-200 bg-red-50 p-4">
      <button onClick={() => setExpanded(!expanded)} className="flex w-full items-center justify-between">
        <div className="flex items-center gap-2">
          <AlertTriangle size={16} className="text-red-600" />
          <span className="text-sm font-bold text-red-800">
            {visible.length} item{visible.length > 1 ? 's' : ''} expiring within 5 days
          </span>
        </div>
        {expanded ? <ChevronUp size={16} className="text-red-400" /> : <ChevronDown size={16} className="text-red-400" />}
      </button>
      {expanded && (
        <div className="mt-3 space-y-2">
          {visible.map((item) => (
            <div key={item.product_id || item.sku} className="flex items-center justify-between rounded-xl bg-white/80 px-4 py-3">
              <div>
                <div className="text-sm font-bold text-stone-900">{item.product_name}</div>
                <div className="mt-0.5 text-xs text-stone-500">
                  {item.days_to_expiry} days left &middot; ~{item.expected_unsold} units at risk
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => handleSendOffer(item)} className="flex items-center gap-1 rounded-lg bg-amber-600 px-3 py-1.5 text-[10px] font-bold text-white hover:bg-amber-500">
                  <Megaphone size={12} /> Send Offer
                </button>
                <button onClick={() => handleDismiss(item.product_id || item.sku)} className="rounded-lg border border-black/10 px-3 py-1.5 text-[10px] font-bold text-stone-500 hover:bg-stone-100">
                  Dismiss
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function MarketIntelSection({ sku, unitPrice }) {
  const [expanded, setExpanded] = useState(false);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showLogForm, setShowLogForm] = useState(false);
  const [logForm, setLogForm] = useState({ source_name: '', price_per_unit: '', unit: 'kg' });
  const [saving, setSaving] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await apiFetch(`/api/market-prices/${sku}`);
      const d = await res.json();
      setData(d);
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  };

  const handleToggle = () => {
    if (!expanded && !data) fetchData();
    setExpanded(!expanded);
  };

  const handleLog = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await apiFetch('/api/market-prices/log', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ product_id: sku, source_name: logForm.source_name, price_per_unit: Number(logForm.price_per_unit), unit: logForm.unit }),
      });
      setShowLogForm(false);
      setLogForm({ source_name: '', price_per_unit: '', unit: 'kg' });
      fetchData();
    } catch (err) { console.error(err); }
    finally { setSaving(false); }
  };

  const delta = data?.median_price && unitPrice ? ((unitPrice - data.median_price) / data.median_price * 100).toFixed(1) : null;
  const isExpensive = delta && Number(delta) > 10;

  return (
    <div className="mt-3 border-t border-black/5 pt-3">
      <button onClick={handleToggle} className="flex w-full items-center justify-between text-xs">
        <span className="flex items-center gap-1.5 font-bold text-teal-700">
          <TrendingUp size={12} />
          Market Intel
        </span>
        {expanded ? <ChevronUp size={12} className="text-stone-400" /> : <ChevronDown size={12} className="text-stone-400" />}
      </button>
      {expanded && (
        <div className="mt-2 space-y-2">
          {loading && <div className="animate-pulse rounded-xl bg-stone-100 py-3 text-center text-xs text-stone-400">Loading...</div>}
          {data && data.median_price != null && (
            <div className="rounded-xl bg-stone-50 p-3 text-xs">
              <div className="flex justify-between">
                <span className="text-stone-500">Market median</span>
                <span className="font-bold text-stone-900">Rs {data.median_price}</span>
              </div>
              <div className="mt-1 flex justify-between">
                <span className="text-stone-500">Lowest seen</span>
                <span className="font-bold text-stone-900">Rs {data.lowest_price} <span className="font-normal text-stone-400">({data.lowest_source})</span></span>
              </div>
              <div className="mt-1 flex justify-between">
                <span className="text-stone-500">Your sell price</span>
                <span className={`font-bold ${isExpensive ? 'text-red-600' : 'text-emerald-700'}`}>
                  Rs {unitPrice} {delta && <span className="text-[10px]">({delta > 0 ? '+' : ''}{delta}%)</span>}
                </span>
              </div>
              <div className="mt-1 flex justify-between">
                <span className="text-stone-500">Confidence</span>
                <span className={`font-bold ${data.confidence === 'high' ? 'text-emerald-600' : data.confidence === 'medium' ? 'text-amber-600' : 'text-stone-400'}`}>
                  {data.confidence}
                </span>
              </div>
            </div>
          )}
          {data && data.median_price == null && !loading && (
            <div className="rounded-xl bg-stone-50 p-3 text-center text-xs text-stone-400">No market data yet</div>
          )}
          {!showLogForm ? (
            <button onClick={() => setShowLogForm(true)} className="w-full rounded-xl border border-dashed border-black/10 py-2 text-[10px] font-bold uppercase tracking-widest text-stone-500 hover:bg-stone-50">
              + Log Competitor Price
            </button>
          ) : (
            <form onSubmit={handleLog} className="space-y-2 rounded-xl border border-black/10 bg-white p-3">
              <input required value={logForm.source_name} onChange={(e) => setLogForm(p => ({ ...p, source_name: e.target.value }))} placeholder="Source (e.g. Big Bazaar)" className="w-full rounded-lg border border-black/10 px-3 py-2 text-xs focus:outline-none" />
              <div className="flex gap-2">
                <input required type="number" min="0" step="0.01" value={logForm.price_per_unit} onChange={(e) => setLogForm(p => ({ ...p, price_per_unit: e.target.value }))} placeholder="Price" className="flex-1 rounded-lg border border-black/10 px-3 py-2 text-xs focus:outline-none" />
                <select value={logForm.unit} onChange={(e) => setLogForm(p => ({ ...p, unit: e.target.value }))} className="rounded-lg border border-black/10 px-2 py-2 text-xs">
                  <option value="kg">kg</option><option value="unit">unit</option><option value="L">L</option>
                </select>
              </div>
              <div className="flex gap-2">
                <button type="button" onClick={() => setShowLogForm(false)} className="flex-1 rounded-lg py-2 text-xs font-bold text-stone-500 hover:bg-stone-50">Cancel</button>
                <button type="submit" disabled={saving} className="flex-1 rounded-lg bg-teal-700 py-2 text-xs font-bold text-white hover:bg-teal-600 disabled:opacity-50">{saving ? 'Saving...' : 'Log'}</button>
              </div>
            </form>
          )}
        </div>
      )}
    </div>
  );
}

function InventoryCard({ item, updating, editingSku, draftImageUrl, savingImage, onStockChange, onStartEdit, onCancelEdit, onDraftChange, onSaveImage }) {
  const [imageSrc, setImageSrc] = useState(item.image_url);
  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageFailed, setImageFailed] = useState(!item.image_url);

  useEffect(() => {
    setImageLoaded(false);
    setImageFailed(!item.image_url);
    setImageSrc(item.image_url);
  }, [item.image_url]);

  const handleImageError = () => {
    setImageFailed(true);
    setImageLoaded(true);
  };

  const catStyle = CATEGORY_STYLES[item.category] || CATEGORY_STYLES.Other;
  const isEditing = editingSku === item.sku;

  return (
    <motion.div
      key={item.sku}
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="group relative overflow-hidden rounded-lg atelier-panel text-[var(--text)] shadow-[0_28px_70px_rgba(0,0,0,0.16)] transition-colors hover:bg-[rgba(55,58,56,0.72)]"
    >
      <div className="relative h-40 overflow-hidden rounded-t-lg border-b border-[rgba(67,72,72,0.18)] bg-[var(--surface-high)]">
        {imageFailed || !imageSrc ? (
          <div className={`flex h-full w-full items-center justify-center bg-gradient-to-br ${catStyle.gradient}`}>
            <span className="text-6xl drop-shadow-lg">{catStyle.emoji}</span>
          </div>
        ) : (
          <>
            {!imageLoaded && (
              <div className="absolute inset-0 animate-pulse bg-gradient-to-r from-[var(--surface-low)] via-[var(--surface-high)] to-[var(--surface-low)]" />
            )}
            <img
              src={imageSrc}
              alt={item.product_name}
              className={`h-full w-full object-cover transition-opacity duration-300 ${imageLoaded ? 'opacity-100' : 'opacity-0'}`}
              onLoad={() => setImageLoaded(true)}
              onError={handleImageError}
            />
          </>
        )}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-20 bg-gradient-to-t from-black/30 to-transparent" />
        <button
          type="button"
          onClick={() => onStartEdit(item)}
          className="absolute right-3 top-3 inline-flex items-center gap-2 rounded-sm border border-[rgba(215,193,194,0.28)] bg-[rgba(12,15,14,0.72)] px-3 py-1.5 text-xs font-bold text-[var(--primary)] opacity-0 shadow-sm transition-all hover:bg-[rgba(25,28,27,0.95)] group-hover:opacity-100"
        >
          <ImagePlus size={14} />
          Edit Image
        </button>

        {isEditing && (
          <div className="absolute inset-x-3 top-14 z-10 rounded-md border border-[rgba(67,72,72,0.2)] bg-[rgba(12,15,14,0.96)] p-3 shadow-xl">
            <div className="mb-2 flex items-center justify-between gap-3">
              <div className="atelier-label text-[10px] text-[#8d9192]">Update product image</div>
              <button type="button" onClick={onCancelEdit} className="text-[#8d9192] transition-colors hover:text-[var(--text)]">
                <X size={14} />
              </button>
            </div>
            <div className="relative">
              <Link2 size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#8d9192]" />
              <input
                type="url"
                value={draftImageUrl}
                onChange={(e) => onDraftChange(e.target.value)}
                placeholder="Paste image URL"
                className="w-full rounded-sm border-0 bg-[var(--surface-highest)] py-2.5 pl-9 pr-3 text-sm text-[var(--text)] placeholder:text-[#8d9192] focus:outline-none"
              />
            </div>
            <div className="mt-3 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={onCancelEdit}
                className="rounded-sm px-3 py-2 text-xs font-bold uppercase tracking-widest text-[#8d9192] transition-colors hover:bg-[var(--surface-low)] hover:text-[var(--text)]"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => onSaveImage(item.sku)}
                disabled={savingImage === item.sku}
                className="rounded-sm bg-[var(--primary)] px-3 py-2 text-xs font-bold uppercase tracking-widest text-[var(--primary-ink)] transition-colors hover:brightness-105 disabled:opacity-50"
              >
                {savingImage === item.sku ? 'Saving...' : 'Save Image'}
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="p-5">
        <div className="mb-4 flex items-start justify-between">
          <div>
            <div className="mb-1 atelier-label text-[10px] text-[#8d9192]">{item.sku}</div>
            <h3 className="pr-8 font-display text-2xl font-light italic leading-tight text-[var(--text)]">{item.product_name}</h3>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="rounded-sm bg-[var(--surface-high)] px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-[#8d9192]">
                {item.category}
              </span>
              <span className="text-xs font-semibold text-[var(--primary)]">₹{item.unit_price}</span>
            </div>
          </div>
          <div className={`rounded-sm border p-2 ${
            item.status === 'critical' ? 'border-[rgba(255,180,171,0.35)] bg-[rgba(147,0,10,0.18)] text-[#ffb4ab]' :
            item.status === 'warning' ? 'border-[rgba(233,226,213,0.3)] bg-[rgba(74,70,61,0.4)] text-[#e9e2d5]' :
            'border-[rgba(139,211,212,0.3)] bg-[rgba(0,57,58,0.5)] text-[#8bd3d4]'
          }`}>
            {item.status === 'critical' ? <PackageX size={18} /> :
             item.status === 'warning' ? <AlertTriangle size={18} /> :
             <CheckCircle size={18} />}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="mb-2 atelier-label text-[10px] text-[#8d9192]">Current Stock</div>
            <div className="flex items-center gap-2">
              <div className="flex shrink-0 items-center overflow-hidden rounded-sm border border-[rgba(67,72,72,0.2)] bg-[var(--surface-low)]">
                <button 
                  onClick={() => onStockChange(item.sku, item.current_stock - 5)}
                  disabled={updating === item.sku}
                  title="Decrease by 5"
                  className="p-1 px-2 text-[#8d9192] transition-colors hover:bg-[var(--surface-high)] hover:text-[var(--text)] disabled:opacity-50"
                >
                  <Minus size={14} />
                </button>
                <span className={`min-w-[2.5ch] px-2 text-center text-lg font-black ${
                  item.status === 'critical' ? 'text-red-700' : 
                  item.status === 'warning' ? 'text-[#e9e2d5]' : 'text-[var(--text)]'
                }`}>
                  {updating === item.sku ? '...' : item.current_stock}
                </span>
                <button 
                  onClick={() => onStockChange(item.sku, item.current_stock + 5)}
                  disabled={updating === item.sku}
                  title="Increase by 5"
                  className="p-1 px-2 text-[#8d9192] transition-colors hover:bg-[var(--surface-high)] hover:text-[var(--text)] disabled:opacity-50"
                >
                  <Plus size={14} />
                </button>
              </div>
              <span className="ml-1 whitespace-nowrap pt-1 text-[10px] font-bold uppercase tracking-wider text-[#8d9192]">
                Min: {item.threshold}
              </span>
            </div>
          </div>
          <div>
            <div className="mb-1 atelier-label text-[10px] text-[#8d9192]">Velocity</div>
            <div className="font-bold text-[var(--text)]">{item.daily_sales_rate} <span className="text-xs font-medium text-[#8d9192]">/day</span></div>
            <div className="mt-2 text-[11px] text-[#8d9192]">Barcode: {item.barcode || 'Not set'}</div>
          </div>
        </div>

        <div className="mt-4 flex items-center justify-between border-t border-[rgba(67,72,72,0.18)] pt-4">
          <span className="text-xs font-semibold text-[#8d9192]">Days until empty</span>
          <span className={`text-sm font-black ${
            item.days_until_stockout < 2 ? 'text-red-700' :
            item.days_until_stockout < 5 ? 'text-amber-700' : 'text-emerald-700'
          }`}>
            {item.days_until_stockout === 'Infinity' ? '∞' : item.days_until_stockout} days
          </span>
        </div>

        <MarketIntelSection sku={item.sku} unitPrice={item.unit_price} />
      </div>

      {item.status === 'critical' && (
        <div className="pointer-events-none absolute right-0 top-0 h-16 w-16">
          <div className="absolute right-0 top-0 m-3 h-2 w-2 rounded-full bg-red-500 shadow-[0_0_12px_rgba(239,68,68,0.8)] animate-pulse" />
        </div>
      )}
    </motion.div>
  );
}

function RegisterProductModal({
  inventory,
  form,
  submitting,
  imagePreviewError,
  onClose,
  onChange,
  onSubmit,
  onSuggestSku,
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="w-full max-w-3xl rounded-lg border border-[rgba(67,72,72,0.18)] bg-[rgba(17,20,19,0.96)] p-6 text-[var(--text)] shadow-[0_30px_100px_rgba(0,0,0,0.3)] lg:p-8">
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <div className="atelier-label text-[10px] text-[#8bd3d4]">Inventory setup</div>
            <h2 className="font-display mt-2 text-4xl font-light italic tracking-tight">Register New Product</h2>
            <p className="mt-2 text-sm leading-relaxed text-[var(--text-muted)]">
              Add a new item to inventory with pricing, threshold, image, and barcode details.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-sm border border-[rgba(67,72,72,0.2)] bg-[var(--surface-low)] p-2 text-[#8d9192] transition-colors hover:text-[var(--text)]"
          >
            <X size={16} />
          </button>
        </div>

        <form className="space-y-5" onSubmit={onSubmit}>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-2">
              <span className="text-xs font-black uppercase tracking-[0.18em] text-stone-500">Product Name</span>
              <input
                required
                type="text"
                value={form.product_name}
                onChange={(e) => onChange('product_name', e.target.value)}
                className="w-full rounded-2xl border border-black/10 bg-white/85 px-4 py-3 text-sm text-stone-900 placeholder:text-stone-400 focus:border-teal-600/50 focus:outline-none"
                placeholder="e.g. Amul Greek Yogurt"
              />
            </label>

            <label className="space-y-2">
              <span className="text-xs font-black uppercase tracking-[0.18em] text-stone-500">Category</span>
              <select
                value={form.category}
                onChange={(e) => onChange('category', e.target.value)}
                className="w-full rounded-2xl border border-black/10 bg-white/85 px-4 py-3 text-sm text-stone-900 focus:border-teal-600/50 focus:outline-none"
              >
                {CATEGORY_OPTIONS.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </label>

            <label className="space-y-2">
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs font-black uppercase tracking-[0.18em] text-stone-500">SKU</span>
                <button
                  type="button"
                  onClick={onSuggestSku}
                  className="text-[10px] font-black uppercase tracking-widest text-teal-700 transition-colors hover:text-teal-600"
                >
                  Suggest
                </button>
              </div>
              <input
                required
                type="text"
                value={form.sku}
                onChange={(e) => onChange('sku', e.target.value.toUpperCase())}
                className="w-full rounded-2xl border border-black/10 bg-white/85 px-4 py-3 text-sm text-stone-900 placeholder:text-stone-400 focus:border-teal-600/50 focus:outline-none"
                placeholder={getSuggestedSku(form.category, inventory)}
              />
            </label>

            <label className="space-y-2">
              <span className="text-xs font-black uppercase tracking-[0.18em] text-stone-500">Unit Price Rs</span>
              <input
                required
                min="0"
                step="0.01"
                type="number"
                value={form.unit_price}
                onChange={(e) => onChange('unit_price', e.target.value)}
                className="w-full rounded-2xl border border-black/10 bg-white/85 px-4 py-3 text-sm text-stone-900 placeholder:text-stone-400 focus:border-teal-600/50 focus:outline-none"
                placeholder="0.00"
              />
            </label>

            <label className="space-y-2">
              <span className="text-xs font-black uppercase tracking-[0.18em] text-stone-500">Opening Stock</span>
              <input
                required
                min="0"
                type="number"
                value={form.current_stock}
                onChange={(e) => onChange('current_stock', e.target.value)}
                className="w-full rounded-2xl border border-black/10 bg-white/85 px-4 py-3 text-sm text-stone-900 placeholder:text-stone-400 focus:border-teal-600/50 focus:outline-none"
              />
            </label>

            <label className="space-y-2">
              <span className="text-xs font-black uppercase tracking-[0.18em] text-stone-500">Minimum Threshold</span>
              <input
                required
                min="0"
                type="number"
                value={form.threshold}
                onChange={(e) => onChange('threshold', e.target.value)}
                className="w-full rounded-2xl border border-black/10 bg-white/85 px-4 py-3 text-sm text-stone-900 placeholder:text-stone-400 focus:border-teal-600/50 focus:outline-none"
              />
            </label>

            <label className="space-y-2">
              <span className="text-xs font-black uppercase tracking-[0.18em] text-stone-500">Expected Daily Sales</span>
              <input
                required
                min="0"
                type="number"
                value={form.daily_sales_rate}
                onChange={(e) => onChange('daily_sales_rate', e.target.value)}
                className="w-full rounded-2xl border border-black/10 bg-white/85 px-4 py-3 text-sm text-stone-900 placeholder:text-stone-400 focus:border-teal-600/50 focus:outline-none"
              />
            </label>

            <label className="space-y-2">
              <span className="text-xs font-black uppercase tracking-[0.18em] text-stone-500">Barcode</span>
              <input
                type="text"
                value={form.barcode}
                onChange={(e) => onChange('barcode', e.target.value)}
                className="w-full rounded-2xl border border-black/10 bg-white/85 px-4 py-3 text-sm text-stone-900 placeholder:text-stone-400 focus:border-teal-600/50 focus:outline-none"
                placeholder="Optional"
              />
            </label>
          </div>

          <div className="grid gap-4 lg:grid-cols-[1fr_220px]">
            <label className="space-y-2">
              <span className="text-xs font-black uppercase tracking-[0.18em] text-stone-500">Image URL</span>
              <input
                type="url"
                value={form.image_url}
                onChange={(e) => onChange('image_url', e.target.value)}
                className="w-full rounded-2xl border border-black/10 bg-white/85 px-4 py-3 text-sm text-stone-900 placeholder:text-stone-400 focus:border-teal-600/50 focus:outline-none"
                placeholder="https://example.com/product.jpg"
              />
            </label>

            <div className="rounded-[24px] border border-black/8 bg-white/80 p-3">
              <div className="text-[10px] font-black uppercase tracking-[0.18em] text-stone-500">Preview</div>
              <div className="mt-2 h-28 overflow-hidden rounded-2xl border border-black/5 bg-stone-100">
                {form.image_url && !imagePreviewError ? (
                  <img
                    src={form.image_url}
                    alt="Preview"
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <div className="flex h-full items-center justify-center text-xs font-semibold text-stone-400">
                    {form.image_url ? 'Image unavailable' : 'No image yet'}
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-2xl px-4 py-3 text-sm font-bold text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-900"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="rounded-2xl bg-teal-700 px-5 py-3 text-sm font-bold text-white transition-colors hover:bg-teal-600 disabled:opacity-50"
            >
              {submitting ? 'Registering...' : 'Register Product'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function InventoryTab() {
  const [inventory, setInventory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [updating, setUpdating] = useState(null);
  const [editingSku, setEditingSku] = useState(null);
  const [draftImageUrl, setDraftImageUrl] = useState('');
  const [savingImage, setSavingImage] = useState(null);
  const [showRegisterModal, setShowRegisterModal] = useState(false);
  const [submittingProduct, setSubmittingProduct] = useState(false);
  const [imagePreviewError, setImagePreviewError] = useState(false);
  const [toast, setToast] = useState('');
  const [registerForm, setRegisterForm] = useState({
    product_name: '',
    sku: '',
    category: 'Dairy',
    unit_price: '',
    current_stock: '',
    threshold: '',
    daily_sales_rate: '',
    barcode: '',
    image_url: '',
  });

  const fetchInventory = async () => {
    setLoading(true);
    try {
      setInventory(await apiFetchArray('/api/inventory'));
    } catch (err) {
      console.error(err);
      setInventory([]);
    } finally {
      setLoading(false);
    }
  };

  const startImageEdit = (item) => {
    setEditingSku(item.sku);
    setDraftImageUrl(item.image_url || '');
  };

  const cancelImageEdit = () => {
    setEditingSku(null);
    setDraftImageUrl('');
  };

  const saveImage = async (sku) => {
    setSavingImage(sku);
    try {
      const response = await apiFetch(`/api/inventory/${sku}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_url: draftImageUrl.trim() || null })
      });

      if (!response.ok) {
        throw new Error('Failed to save image URL');
      }

      const updated = await response.json();
      setInventory((prev) => prev.map((item) => (
        item.sku === sku ? { ...item, image_url: updated.image_url } : item
      )));
      cancelImageEdit();
    } catch (err) {
      console.error('Failed to save image:', err);
    } finally {
      setSavingImage(null);
    }
  };

  const handleStockChange = async (sku, newQuantity) => {
    if (newQuantity < 0) return;
    setUpdating(sku);
    try {
      const response = await apiFetch('/api/inventory/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sku, quantity: newQuantity })
      });
      if (response.ok) {
        // optimistically update local state to avoid full reload delay
        setInventory(prev => prev.map(item => 
          item.sku === sku ? { ...item, current_stock: newQuantity } : item
        ));
      }
    } catch (err) {
      console.error('Failed to update stock:', err);
    } finally {
      setUpdating(null);
    }
  };

  useEffect(() => {
    fetchInventory();
  }, []);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = setTimeout(() => setToast(''), 2200);
    return () => clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    if (!showRegisterModal) return;
    if (!registerForm.sku || registerForm.sku === getSuggestedSku(registerForm.category, inventory)) {
      setRegisterForm((prev) => ({ ...prev, sku: getSuggestedSku(prev.category, inventory) }));
    }
  }, [registerForm.category, inventory, showRegisterModal]);

  const filtered = (Array.isArray(inventory) ? inventory : []).filter(item =>
    item.product_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    item.sku?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const openRegisterModal = () => {
    setRegisterForm({
      product_name: '',
      sku: getSuggestedSku('Dairy', inventory),
      category: 'Dairy',
      unit_price: '',
      current_stock: '',
      threshold: '',
      daily_sales_rate: '',
      barcode: '',
      image_url: '',
    });
    setImagePreviewError(false);
    setShowRegisterModal(true);
  };

  const closeRegisterModal = () => {
    setShowRegisterModal(false);
    setSubmittingProduct(false);
    setImagePreviewError(false);
  };

  const updateRegisterForm = (field, value) => {
    if (field === 'image_url') {
      setImagePreviewError(false);
    }
    setRegisterForm((prev) => {
      if (field === 'category') {
        const previousSuggested = getSuggestedSku(prev.category, inventory);
        const nextSuggested = getSuggestedSku(value, inventory);
        return {
          ...prev,
          category: value,
          sku: !prev.sku || prev.sku === previousSuggested ? nextSuggested : prev.sku,
        };
      }
      return { ...prev, [field]: value };
    });
  };

  const handleRegisterProduct = async (event) => {
    event.preventDefault();
    setSubmittingProduct(true);
    try {
      const payload = {
        sku: registerForm.sku.trim(),
        product_name: registerForm.product_name.trim(),
        category: registerForm.category,
        unit_price: Number(registerForm.unit_price),
        current_stock: Number(registerForm.current_stock),
        threshold: Number(registerForm.threshold),
        daily_sales_rate: Number(registerForm.daily_sales_rate),
        barcode: registerForm.barcode.trim() || null,
        image_url: registerForm.image_url.trim() || null,
      };

      const response = await apiFetch('/api/inventory/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error('Failed to register product');
      }

      await fetchInventory();
      closeRegisterModal();
      setToast(`✅ ${payload.product_name} registered`);
    } catch (err) {
      console.error('Failed to register product:', err);
    } finally {
      setSubmittingProduct(false);
    }
  };

  return (
    <div className="space-y-8">
      <ExpiryAlertsBanner />

      <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between">
        <div className="relative flex-1 max-w-md">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#8d9192]" />
          <input
            type="text"
            placeholder="Search by name or SKU..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            className="w-full rounded-sm border-0 bg-[var(--surface-highest)] py-2.5 pl-10 pr-4 text-sm text-[var(--text)] transition-colors placeholder:text-[#8d9192] focus:outline-none"
          />
        </div>
        <button 
          onClick={fetchInventory}
          disabled={loading}
          className="flex items-center gap-2 rounded-sm border border-[rgba(67,72,72,0.22)] bg-[var(--surface-low)] px-4 py-2.5 text-sm font-semibold text-[var(--text)] transition-all hover:bg-[var(--surface-high)] disabled:opacity-50"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin text-[#8bd3d4]' : 'text-[#8bd3d4]'} />
          Refresh
        </button>
        <button
          onClick={openRegisterModal}
          className="flex items-center gap-2 rounded-sm bg-[var(--primary)] px-4 py-2.5 text-sm font-semibold text-[var(--primary-ink)] transition-colors hover:brightness-105"
        >
          <Plus size={16} />
          Register New Product
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map(item => (
          <InventoryCard
            key={item.sku}
            item={item}
            updating={updating}
            editingSku={editingSku}
            draftImageUrl={draftImageUrl}
            savingImage={savingImage}
            onStockChange={handleStockChange}
            onStartEdit={startImageEdit}
            onCancelEdit={cancelImageEdit}
            onDraftChange={setDraftImageUrl}
            onSaveImage={saveImage}
          />
        ))}
        {filtered.length === 0 && !loading && (
          <div className="col-span-full rounded-lg atelier-panel p-8 py-12 text-center">
            <PackageX size={32} className="mx-auto mb-3 text-[#8d9192]" />
            <h3 className="mb-1 font-semibold text-[var(--text)]">No items found</h3>
            <p className="text-sm text-[var(--text-muted)]">Try adjusting your search</p>
          </div>
        )}
      </div>

      {showRegisterModal && (
        <RegisterProductModal
          inventory={inventory}
          form={registerForm}
          submitting={submittingProduct}
          imagePreviewError={imagePreviewError}
          onClose={closeRegisterModal}
          onChange={updateRegisterForm}
          onSubmit={handleRegisterProduct}
          onSuggestSku={() => setRegisterForm((prev) => ({ ...prev, sku: getSuggestedSku(prev.category, inventory) }))}
        />
      )}

      {showRegisterModal && registerForm.image_url && (
        <img
          src={registerForm.image_url}
          alt=""
          className="hidden"
          onLoad={() => setImagePreviewError(false)}
          onError={() => setImagePreviewError(true)}
        />
      )}

      {toast && (
        <div className="fixed bottom-6 right-6 z-50 rounded-sm border border-[rgba(139,211,212,0.28)] bg-[rgba(12,15,14,0.96)] px-4 py-3 text-sm font-bold text-[#8bd3d4] shadow-[0_20px_50px_rgba(0,0,0,0.22)]">
          {toast}
        </div>
      )}
    </div>
  );
}
