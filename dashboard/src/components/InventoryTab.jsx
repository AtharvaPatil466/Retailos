import React, { useState, useEffect } from 'react';
import { Package, AlertTriangle, RefreshCw, PackageX, CheckCircle, Search, Plus, Minus } from 'lucide-react';
import { motion } from 'framer-motion';

export default function InventoryTab() {
  const [inventory, setInventory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');

  const [updating, setUpdating] = useState(null);

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

  const filtered = inventory.filter(item => 
    item.product_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    item.sku?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between">
        <div className="relative flex-1 max-w-md">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40" />
          <input
            type="text"
            placeholder="Search by name or SKU..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 bg-white/[0.03] border border-white/10 rounded-xl focus:outline-none focus:border-blue-500/50 text-sm transition-colors text-white"
          />
        </div>
        <button 
          onClick={fetchInventory}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2.5 bg-white/[0.03] hover:bg-white/[0.08] border border-white/10 rounded-xl text-sm font-semibold transition-all disabled:opacity-50 text-white"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin text-blue-400' : 'text-blue-400'} />
          Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map(item => (
          <motion.div 
            key={item.sku}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="p-5 rounded-2xl border border-white/5 bg-[#0a0a0a]/50 relative overflow-hidden group hover:border-white/10 transition-colors"
          >
            <div className="flex items-start justify-between mb-4">
              <div>
                <div className="text-xs font-bold text-white/40 mb-1">{item.sku}</div>
                <h3 className="font-bold text-base leading-tight pr-8">{item.product_name}</h3>
              </div>
              <div className={`p-2 rounded-xl border ${
                item.status === 'critical' ? 'bg-red-500/10 border-red-500/20 text-red-500' :
                item.status === 'warning' ? 'bg-amber-500/10 border-amber-500/20 text-amber-500' :
                'bg-green-500/10 border-green-500/20 text-green-500'
              }`}>
                {item.status === 'critical' ? <PackageX size={18} /> :
                 item.status === 'warning' ? <AlertTriangle size={18} /> :
                 <CheckCircle size={18} />}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="text-[10px] uppercase font-bold text-white/30 tracking-wider mb-2">Current Stock</div>
                <div className="flex items-center gap-2">
                  <div className="flex items-center bg-white/[0.03] border border-white/10 rounded-lg overflow-hidden shrink-0">
                    <button 
                      onClick={() => handleStockChange(item.sku, item.current_stock - 5)}
                      disabled={updating === item.sku}
                      title="Decrease by 5"
                      className="p-1 px-2 hover:bg-white/10 text-white/40 hover:text-white transition-colors disabled:opacity-50"
                    >
                      <Minus size={14} />
                    </button>
                    <span className={`px-2 text-lg font-black text-center min-w-[2.5ch] ${
                      item.status === 'critical' ? 'text-red-400' : 
                      item.status === 'warning' ? 'text-amber-400' : 'text-white'
                    }`}>
                      {updating === item.sku ? '...' : item.current_stock}
                    </span>
                    <button 
                      onClick={() => handleStockChange(item.sku, item.current_stock + 5)}
                      disabled={updating === item.sku}
                      title="Increase by 5"
                      className="p-1 px-2 hover:bg-white/10 text-white/40 hover:text-white transition-colors disabled:opacity-50"
                    >
                      <Plus size={14} />
                    </button>
                  </div>
                  <span className="text-[10px] uppercase tracking-wider text-white/40 font-bold whitespace-nowrap ml-1 pt-1 opacity-70">
                    Min: {item.threshold}
                  </span>
                </div>
              </div>
              <div>
                <div className="text-[10px] uppercase font-bold text-white/30 tracking-wider mb-1">Velocity</div>
                <div className="font-bold text-white/80">{item.daily_sales_rate} <span className="text-xs text-white/40 font-medium">/day</span></div>
              </div>
            </div>

            <div className="mt-4 pt-4 border-t border-white/5 flex items-center justify-between">
              <span className="text-xs font-semibold text-white/50">Days until empty</span>
              <span className={`text-sm font-black ${
                item.days_until_stockout < 2 ? 'text-red-400' :
                item.days_until_stockout < 5 ? 'text-amber-400' : 'text-green-400'
              }`}>
                {item.days_until_stockout === 'Infinity' ? '∞' : item.days_until_stockout} days
              </span>
            </div>
            
            {item.status === 'critical' && (
              <div className="absolute top-0 right-0 w-16 h-16 pointer-events-none">
                <div className="absolute top-0 right-0 w-2 h-2 rounded-full bg-red-500 m-3 shadow-[0_0_12px_rgba(239,68,68,0.8)] animate-pulse" />
              </div>
            )}
          </motion.div>
        ))}
        {filtered.length === 0 && !loading && (
          <div className="col-span-full py-12 text-center border border-dashed border-white/10 rounded-2xl p-6 bg-white/[0.02]">
            <PackageX size={32} className="mx-auto text-white/20 mb-3" />
            <h3 className="text-white/60 font-semibold mb-1">No items found</h3>
            <p className="text-white/40 text-sm">Try adjusting your search</p>
          </div>
        )}
      </div>
    </div>
  );
}
