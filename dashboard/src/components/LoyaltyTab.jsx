import React, { useState, useEffect } from 'react';
import { Award, Star, Gift, TrendingUp } from 'lucide-react';

const getApiBase = () => (typeof window !== 'undefined' ? window.location.origin : '');

const TIER_COLORS = {
  bronze: 'text-orange-400',
  silver: 'text-gray-300',
  gold: 'text-yellow-400',
  platinum: 'text-purple-400',
};

export default function LoyaltyTab() {
  const api = getApiBase();
  const [catalog, setCatalog] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch(`${api}/api/loyalty/catalog`).then((r) => r.json()),
      fetch(`${api}/api/loyalty/catalog/categories`).then((r) => r.json()),
    ])
      .then(([cat, cats]) => {
        setCatalog(cat.products || []);
        setCategories(cats.categories || []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [api]);

  if (loading) return <div className="p-6 text-gray-400">Loading loyalty...</div>;

  return (
    <div className="p-6 space-y-6">
      <h2 className="text-xl font-bold text-white flex items-center gap-2">
        <Award size={20} /> Loyalty Program
      </h2>

      {/* Tier Info */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {['bronze', 'silver', 'gold', 'platinum'].map((tier) => (
          <div key={tier} className="bg-gray-800 rounded-lg p-4 text-center">
            <Star className={`mx-auto mb-2 ${TIER_COLORS[tier]}`} size={24} />
            <div className={`font-bold capitalize ${TIER_COLORS[tier]}`}>{tier}</div>
            <div className="text-xs text-gray-400">
              {tier === 'bronze' && '0+ pts'}
              {tier === 'silver' && '500+ pts'}
              {tier === 'gold' && '2000+ pts'}
              {tier === 'platinum' && '5000+ pts'}
            </div>
          </div>
        ))}
      </div>

      {/* Categories */}
      {categories.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {categories.map((cat) => (
            <span
              key={cat}
              className="bg-gray-700 text-gray-300 px-3 py-1 rounded-full text-xs"
            >
              {cat}
            </span>
          ))}
        </div>
      )}

      {/* Catalog */}
      <div className="bg-gray-800 rounded-lg overflow-hidden">
        <h3 className="text-white font-semibold p-4 border-b border-gray-700">
          Product Catalog ({catalog.length} products)
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 p-4">
          {catalog.slice(0, 12).map((p, i) => (
            <div key={i} className="bg-gray-700 rounded-lg p-3">
              <div className="text-white font-medium text-sm">{p.product_name || p.name}</div>
              <div className="text-gray-400 text-xs mt-1">{p.category}</div>
              <div className="flex justify-between items-center mt-2">
                <span className="text-green-400 font-bold">₹{(p.unit_price || p.price || 0).toFixed(2)}</span>
                <span className={`text-xs ${p.current_stock > 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {p.current_stock > 0 ? `${p.current_stock} in stock` : 'Out of stock'}
                </span>
              </div>
            </div>
          ))}
        </div>
        {catalog.length === 0 && (
          <div className="p-6 text-center text-gray-500">No products in catalog</div>
        )}
      </div>
    </div>
  );
}
