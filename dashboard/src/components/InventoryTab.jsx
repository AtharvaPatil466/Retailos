import React, { useState, useEffect } from 'react';
import { Package, AlertTriangle, RefreshCw, PackageX, CheckCircle, Search, Plus, Minus, ImagePlus, Link2, X, ChevronDown, ChevronUp, Megaphone, TrendingDown, TrendingUp } from 'lucide-react';
import { motion } from 'framer-motion';

const CATEGORY_OPTIONS = ['Dairy', 'Frozen', 'Snacks', 'Beverages', 'Staples', 'Household', 'Personal Care', 'Other'];

function getFallbackImage(productName) {
  return `https://source.unsplash.com/300x200/?${encodeURIComponent(productName)},food`;
}

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
    fetch('/api/inventory/expiry-risks')
      .then((r) => r.json())
      .then((data) => setRisks(data || []))
      .catch(() => {});
  }, []);

  const handleDismiss = (sku) => {
    const next = { ...dismissed, [sku]: Date.now() };
    setDismissed(next);
    localStorage.setItem('expiry_dismissed', JSON.stringify(next));
  };

  const handleSendOffer = async (item) => {
    try {
      await fetch('/api/events', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'expiry_offer', data: { sku: item.product_id || item.sku, product_name: item.product_name } }),
      });
    } catch (err) { console.error(err); }
  };

  const visible = risks.filter((r) => (r.days_to_expiry <= 5) && !dismissed[r.product_id || r.sku]);
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
      const res = await fetch(`/api/market-prices/${sku}`);
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
      await fetch('/api/market-prices/log', {
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
  const [imageSrc, setImageSrc] = useState(item.image_url || getFallbackImage(item.product_name));
  const [imageLoaded, setImageLoaded] = useState(false);

  useEffect(() => {
    setImageLoaded(false);
    setImageSrc(item.image_url || getFallbackImage(item.product_name));
  }, [item.image_url, item.product_name]);

  const handleImageError = () => {
    const fallback = getFallbackImage(item.product_name);
    if (imageSrc !== fallback) {
      setImageLoaded(false);
      setImageSrc(fallback);
      return;
    }
    setImageLoaded(true);
  };

  const isEditing = editingSku === item.sku;

  return (
    <motion.div
      key={item.sku}
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="group relative overflow-hidden rounded-[28px] border border-black/5 bg-[rgba(255,252,247,0.9)] text-stone-900 shadow-[0_18px_45px_rgba(0,0,0,0.05)] transition-colors hover:bg-white"
    >
      <div className="relative h-40 overflow-hidden rounded-t-[28px] border-b border-black/5 bg-stone-100">
        {!imageLoaded && (
          <div className="absolute inset-0 animate-pulse bg-gradient-to-r from-stone-200 via-stone-100 to-stone-200" />
        )}
        <img
          src={imageSrc}
          alt={item.product_name}
          className={`h-full w-full object-cover transition-opacity duration-300 ${imageLoaded ? 'opacity-100' : 'opacity-0'}`}
          onLoad={() => setImageLoaded(true)}
          onError={handleImageError}
        />
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-20 bg-gradient-to-t from-black/30 to-transparent" />
        <button
          type="button"
          onClick={() => onStartEdit(item)}
          className="absolute right-3 top-3 inline-flex items-center gap-2 rounded-full border border-white/70 bg-white/90 px-3 py-1.5 text-xs font-bold text-stone-700 opacity-0 shadow-sm transition-all hover:bg-white group-hover:opacity-100"
        >
          <ImagePlus size={14} />
          Edit Image
        </button>

        {isEditing && (
          <div className="absolute inset-x-3 top-14 z-10 rounded-2xl border border-black/10 bg-white p-3 shadow-xl">
            <div className="mb-2 flex items-center justify-between gap-3">
              <div className="text-xs font-black uppercase tracking-widest text-stone-500">Update product image</div>
              <button type="button" onClick={onCancelEdit} className="text-stone-400 transition-colors hover:text-stone-700">
                <X size={14} />
              </button>
            </div>
            <div className="relative">
              <Link2 size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" />
              <input
                type="url"
                value={draftImageUrl}
                onChange={(e) => onDraftChange(e.target.value)}
                placeholder="Paste image URL"
                className="w-full rounded-xl border border-black/10 bg-stone-50 py-2.5 pl-9 pr-3 text-sm text-stone-900 placeholder:text-stone-400 focus:border-teal-600/50 focus:outline-none"
              />
            </div>
            <div className="mt-3 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={onCancelEdit}
                className="rounded-xl px-3 py-2 text-xs font-bold uppercase tracking-widest text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-800"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => onSaveImage(item.sku)}
                disabled={savingImage === item.sku}
                className="rounded-xl bg-teal-700 px-3 py-2 text-xs font-bold uppercase tracking-widest text-white transition-colors hover:bg-teal-600 disabled:opacity-50"
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
            <div className="mb-1 text-xs font-bold text-stone-500">{item.sku}</div>
            <h3 className="pr-8 text-base font-bold leading-tight text-stone-900">{item.product_name}</h3>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-stone-100 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-stone-600">
                {item.category}
              </span>
              <span className="text-xs font-semibold text-stone-600">₹{item.unit_price}</span>
            </div>
          </div>
          <div className={`rounded-xl border p-2 ${
            item.status === 'critical' ? 'border-red-200 bg-red-50 text-red-700' :
            item.status === 'warning' ? 'border-amber-200 bg-amber-50 text-amber-700' :
            'border-emerald-200 bg-emerald-50 text-emerald-700'
          }`}>
            {item.status === 'critical' ? <PackageX size={18} /> :
             item.status === 'warning' ? <AlertTriangle size={18} /> :
             <CheckCircle size={18} />}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-stone-500">Current Stock</div>
            <div className="flex items-center gap-2">
              <div className="flex shrink-0 items-center overflow-hidden rounded-lg border border-black/10 bg-white/90">
                <button 
                  onClick={() => onStockChange(item.sku, item.current_stock - 5)}
                  disabled={updating === item.sku}
                  title="Decrease by 5"
                  className="p-1 px-2 text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-900 disabled:opacity-50"
                >
                  <Minus size={14} />
                </button>
                <span className={`min-w-[2.5ch] px-2 text-center text-lg font-black ${
                  item.status === 'critical' ? 'text-red-700' : 
                  item.status === 'warning' ? 'text-amber-700' : 'text-stone-900'
                }`}>
                  {updating === item.sku ? '...' : item.current_stock}
                </span>
                <button 
                  onClick={() => onStockChange(item.sku, item.current_stock + 5)}
                  disabled={updating === item.sku}
                  title="Increase by 5"
                  className="p-1 px-2 text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-900 disabled:opacity-50"
                >
                  <Plus size={14} />
                </button>
              </div>
              <span className="ml-1 whitespace-nowrap pt-1 text-[10px] font-bold uppercase tracking-wider text-stone-500">
                Min: {item.threshold}
              </span>
            </div>
          </div>
          <div>
            <div className="mb-1 text-[10px] font-bold uppercase tracking-wider text-stone-500">Velocity</div>
            <div className="font-bold text-stone-900">{item.daily_sales_rate} <span className="text-xs font-medium text-stone-500">/day</span></div>
            <div className="mt-2 text-[11px] text-stone-500">Barcode: {item.barcode || 'Not set'}</div>
          </div>
        </div>

        <div className="mt-4 flex items-center justify-between border-t border-black/5 pt-4">
          <span className="text-xs font-semibold text-stone-500">Days until empty</span>
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4 backdrop-blur-sm">
      <div className="w-full max-w-3xl rounded-[28px] border border-black/5 bg-[rgba(255,252,247,0.98)] p-6 text-stone-900 shadow-[0_30px_100px_rgba(0,0,0,0.18)] lg:p-8">
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.22em] text-stone-500">Inventory setup</div>
            <h2 className="font-display mt-2 text-3xl font-bold tracking-tight">Register New Product</h2>
            <p className="mt-2 text-sm leading-relaxed text-stone-600">
              Add a new item to inventory with pricing, threshold, image, and barcode details.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-black/10 bg-white/80 p-2 text-stone-500 transition-colors hover:text-stone-900"
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
      const res = await fetch('/api/inventory');
      const data = await res.json();
      setInventory(data || []);
    } catch (err) {
      console.error(err);
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
      const response = await fetch(`/api/inventory/${sku}`, {
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
      const response = await fetch('/api/inventory/update', {
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

  const filtered = inventory.filter(item => 
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

      const response = await fetch('/api/inventory/register', {
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
    <div className="space-y-6">
      <ExpiryAlertsBanner />

      <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between">
        <div className="relative flex-1 max-w-md">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" />
          <input
            type="text"
            placeholder="Search by name or SKU..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            className="w-full rounded-xl border border-black/10 bg-white/80 py-2.5 pl-10 pr-4 text-sm text-stone-900 transition-colors placeholder:text-stone-400 focus:border-teal-600/50 focus:outline-none"
          />
        </div>
        <button 
          onClick={fetchInventory}
          disabled={loading}
          className="flex items-center gap-2 rounded-xl border border-black/10 bg-white/80 px-4 py-2.5 text-sm font-semibold text-stone-700 transition-all hover:bg-white disabled:opacity-50"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin text-teal-700' : 'text-teal-700'} />
          Refresh
        </button>
        <button
          onClick={openRegisterModal}
          className="flex items-center gap-2 rounded-xl bg-teal-700 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-teal-600"
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
          <div className="col-span-full rounded-[28px] border border-dashed border-black/10 bg-white/70 p-8 py-12 text-center">
            <PackageX size={32} className="mx-auto mb-3 text-stone-400" />
            <h3 className="mb-1 font-semibold text-stone-800">No items found</h3>
            <p className="text-sm text-stone-500">Try adjusting your search</p>
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
        <div className="fixed bottom-6 right-6 z-50 rounded-2xl border border-emerald-200 bg-white px-4 py-3 text-sm font-bold text-emerald-700 shadow-[0_20px_50px_rgba(0,0,0,0.12)]">
          {toast}
        </div>
      )}
    </div>
  );
}
