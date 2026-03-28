import React, { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { Minus, Plus, Search, ShoppingCart, Trash2 } from 'lucide-react';

const CATEGORY_FILTERS = ['All', 'Dairy', 'Frozen', 'Snacks', 'Beverages', 'Staples', 'Household', 'Personal Care', 'Other'];

function getFallbackImage(productName) {
  return `https://source.unsplash.com/300x200/?${encodeURIComponent(productName)},food`;
}

function ProductCard({ item, quantityToAdd, onAdjustQuantity, onAddToCart }) {
  const [imageSrc, setImageSrc] = useState(item.image_url || getFallbackImage(item.product_name));
  const [loaded, setLoaded] = useState(false);
  const outOfStock = item.current_stock === 0;

  useEffect(() => {
    setLoaded(false);
    setImageSrc(item.image_url || getFallbackImage(item.product_name));
  }, [item.image_url, item.product_name]);

  const handleImageError = () => {
    const fallback = getFallbackImage(item.product_name);
    if (imageSrc !== fallback) {
      setLoaded(false);
      setImageSrc(fallback);
    } else {
      setLoaded(true);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={`overflow-hidden rounded-[28px] border border-black/5 bg-[rgba(255,252,247,0.92)] shadow-[0_18px_45px_rgba(0,0,0,0.05)] transition-all ${outOfStock ? 'opacity-55 grayscale-[0.2]' : 'hover:bg-white'}`}
    >
      <div className="relative h-40 overflow-hidden border-b border-black/5 bg-stone-100">
        {!loaded && <div className="absolute inset-0 animate-pulse bg-gradient-to-r from-stone-200 via-stone-100 to-stone-200" />}
        <img
          src={imageSrc}
          alt={item.product_name}
          className={`h-full w-full object-cover transition-opacity duration-300 ${loaded ? 'opacity-100' : 'opacity-0'}`}
          onLoad={() => setLoaded(true)}
          onError={handleImageError}
        />
      </div>

      <div className="p-5">
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.18em] text-stone-500">{item.category}</div>
            <h3 className="mt-1 text-base font-bold leading-tight text-stone-900">{item.product_name}</h3>
          </div>
          <span className={`rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider ${outOfStock ? 'bg-red-100 text-red-700' : 'bg-stone-100 text-stone-600'}`}>
            Stock {item.current_stock}
          </span>
        </div>

        <div className="mb-4 flex items-center justify-between">
          <div className="text-xl font-black text-stone-900">Rs {item.unit_price}</div>
          <div className="text-xs text-stone-500">{item.sku}</div>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center overflow-hidden rounded-xl border border-black/10 bg-white">
            <button
              onClick={() => onAdjustQuantity(item.sku, -1)}
              className="px-3 py-2 text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-900"
              disabled={quantityToAdd <= 1}
            >
              <Minus size={14} />
            </button>
            <span className="min-w-[2.5rem] text-center text-sm font-bold text-stone-900">{quantityToAdd}</span>
            <button
              onClick={() => onAdjustQuantity(item.sku, 1)}
              className="px-3 py-2 text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-900"
              disabled={quantityToAdd >= Math.max(item.current_stock, 1)}
            >
              <Plus size={14} />
            </button>
          </div>

          <button
            onClick={() => onAddToCart(item, quantityToAdd)}
            disabled={outOfStock}
            className={`flex-1 rounded-xl px-4 py-3 text-sm font-bold transition-colors ${outOfStock ? 'cursor-not-allowed bg-stone-200 text-stone-400' : 'bg-teal-700 text-white hover:bg-teal-600'}`}
          >
            Add to Cart
          </button>
        </div>
      </div>
    </motion.div>
  );
}

export default function CartTab() {
  const [inventory, setInventory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [category, setCategory] = useState('All');
  const [cart, setCart] = useState([]);
  const [addQuantities, setAddQuantities] = useState({});
  const [submittingSale, setSubmittingSale] = useState(false);
  const [toast, setToast] = useState('');

  const fetchInventory = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/inventory');
      const data = await res.json();
      setInventory(data || []);
      setAddQuantities((prev) => {
        const next = { ...prev };
        for (const item of data || []) {
          if (!next[item.sku]) next[item.sku] = 1;
        }
        return next;
      });
    } catch (error) {
      console.error('Failed to fetch inventory:', error);
    } finally {
      setLoading(false);
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

  const filtered = useMemo(() => (
    inventory.filter((item) => {
      const matchesSearch =
        item.product_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        item.sku?.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesCategory = category === 'All' || item.category === category;
      return matchesSearch && matchesCategory;
    })
  ), [inventory, searchTerm, category]);

  const cartSubtotal = cart.reduce((sum, line) => sum + (line.unit_price * line.qty), 0);

  const adjustAddQuantity = (sku, delta) => {
    const item = inventory.find((entry) => entry.sku === sku);
    const max = Math.max(item?.current_stock || 1, 1);
    setAddQuantities((prev) => {
      const current = prev[sku] || 1;
      const next = Math.min(max, Math.max(1, current + delta));
      return { ...prev, [sku]: next };
    });
  };

  const addToCart = (item, qty) => {
    if (!qty || item.current_stock === 0) return;
    setCart((prev) => {
      const existing = prev.find((line) => line.sku === item.sku);
      const nextQty = Math.min(item.current_stock, (existing?.qty || 0) + qty);
      if (existing) {
        return prev.map((line) => line.sku === item.sku ? { ...line, qty: nextQty } : line);
      }
      return [...prev, {
        sku: item.sku,
        product_name: item.product_name,
        unit_price: item.unit_price,
        qty: Math.min(item.current_stock, qty),
      }];
    });
    setAddQuantities((prev) => ({ ...prev, [item.sku]: 1 }));
  };

  const adjustCartQty = (sku, delta) => {
    const stockItem = inventory.find((item) => item.sku === sku);
    const max = stockItem?.current_stock || 0;
    setCart((prev) => prev.flatMap((line) => {
      if (line.sku !== sku) return [line];
      const nextQty = Math.max(0, Math.min(max, line.qty + delta));
      return nextQty === 0 ? [] : [{ ...line, qty: nextQty }];
    }));
  };

  const removeCartItem = (sku) => {
    setCart((prev) => prev.filter((line) => line.sku !== sku));
  };

  const recordSale = async () => {
    if (!cart.length) return;
    setSubmittingSale(true);
    try {
      const response = await fetch('/api/inventory/sale', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          items: cart.map((line) => ({ sku: line.sku, qty: line.qty })),
        }),
      });
      if (!response.ok) {
        throw new Error('Failed to record sale');
      }
      const result = await response.json();
      setCart([]);
      setToast(`✅ Sale of Rs ${result.total_amount} recorded`);
      await fetchInventory();
    } catch (error) {
      console.error('Failed to record sale:', error);
    } finally {
      setSubmittingSale(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(340px,1fr)]">
        <section className="space-y-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="relative flex-1 max-w-xl">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search products by name or SKU..."
                className="w-full rounded-2xl border border-black/10 bg-white/85 py-3 pl-10 pr-4 text-sm text-stone-900 placeholder:text-stone-400 focus:border-teal-600/50 focus:outline-none"
              />
            </div>
            <button
              onClick={fetchInventory}
              className="rounded-2xl border border-black/10 bg-white/85 px-4 py-3 text-sm font-semibold text-stone-700 transition-colors hover:bg-white"
            >
              Refresh Products
            </button>
          </div>

          <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide lg:flex-wrap">
            {CATEGORY_FILTERS.map((filter) => (
              <button
                key={filter}
                onClick={() => setCategory(filter)}
                className={`rounded-full border px-4 py-2 text-[10px] font-black uppercase tracking-widest transition-all ${
                  category === filter
                    ? 'border-teal-700 bg-teal-700 text-white'
                    : 'border-black/10 bg-white/75 text-stone-600 hover:bg-white hover:text-stone-900'
                }`}
              >
                {filter}
              </button>
            ))}
          </div>

          <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
            {filtered.map((item) => (
              <ProductCard
                key={item.sku}
                item={item}
                quantityToAdd={addQuantities[item.sku] || 1}
                onAdjustQuantity={adjustAddQuantity}
                onAddToCart={addToCart}
              />
            ))}
            {!loading && filtered.length === 0 && (
              <div className="col-span-full rounded-[28px] border border-dashed border-black/10 bg-white/70 p-10 text-center text-stone-500">
                No products match this filter.
              </div>
            )}
          </div>
        </section>

        <aside className="xl:sticky xl:top-28 xl:self-start">
          <div className="rounded-[30px] border border-black/5 bg-[rgba(255,252,247,0.94)] p-5 shadow-[0_20px_55px_rgba(0,0,0,0.06)]">
            <div className="mb-5 flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-teal-100 text-teal-700">
                <ShoppingCart size={20} />
              </div>
              <div>
                <div className="text-[10px] font-black uppercase tracking-[0.18em] text-stone-500">Active Cart</div>
                <h3 className="font-display text-2xl font-bold text-stone-900">Checkout</h3>
              </div>
            </div>

            <div className="space-y-3">
              {cart.length === 0 && (
                <div className="rounded-2xl border border-dashed border-black/10 bg-white/60 p-6 text-center text-sm text-stone-500">
                  Add products from the browser to start a sale.
                </div>
              )}

              {cart.map((line) => (
                <div key={line.sku} className="rounded-2xl border border-black/5 bg-white/85 p-4 shadow-sm">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-bold text-stone-900">{line.product_name}</div>
                      <div className="mt-1 text-xs text-stone-500">Rs {line.unit_price} each</div>
                    </div>
                    <button
                      onClick={() => removeCartItem(line.sku)}
                      className="rounded-full p-1.5 text-stone-400 transition-colors hover:bg-stone-100 hover:text-red-700"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>

                  <div className="mt-4 flex items-center justify-between">
                    <div className="flex items-center overflow-hidden rounded-xl border border-black/10 bg-white">
                      <button onClick={() => adjustCartQty(line.sku, -1)} className="px-3 py-2 text-stone-500 hover:bg-stone-100 hover:text-stone-900">
                        <Minus size={14} />
                      </button>
                      <span className="min-w-[2.5rem] text-center text-sm font-bold text-stone-900">{line.qty}</span>
                      <button onClick={() => adjustCartQty(line.sku, 1)} className="px-3 py-2 text-stone-500 hover:bg-stone-100 hover:text-stone-900">
                        <Plus size={14} />
                      </button>
                    </div>
                    <div className="text-sm font-black text-stone-900">Rs {(line.qty * line.unit_price).toFixed(2)}</div>
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-6 border-t border-black/5 pt-5">
              <div className="mb-4 flex items-center justify-between text-sm">
                <span className="font-semibold text-stone-500">Subtotal</span>
                <span className="text-xl font-black text-stone-900">Rs {cartSubtotal.toFixed(2)}</span>
              </div>
              <button
                onClick={recordSale}
                disabled={!cart.length || submittingSale}
                className="w-full rounded-2xl bg-teal-700 px-4 py-3 text-sm font-bold text-white transition-colors hover:bg-teal-600 disabled:cursor-not-allowed disabled:bg-stone-300"
              >
                {submittingSale ? 'Recording Sale...' : 'Record Sale'}
              </button>
            </div>
          </div>
        </aside>
      </div>

      {toast && (
        <div className="fixed bottom-6 right-6 z-50 rounded-2xl border border-emerald-200 bg-white px-4 py-3 text-sm font-bold text-emerald-700 shadow-[0_20px_50px_rgba(0,0,0,0.12)]">
          {toast}
        </div>
      )}
    </div>
  );
}
