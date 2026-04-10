import React, { useState, useEffect } from 'react';
import { IndianRupee, CreditCard, Smartphone, Banknote } from 'lucide-react';

const getApiBase = () => (typeof window !== 'undefined' ? window.location.origin : '');
const getToken = () => {
  try {
    return localStorage.getItem('retailos_token') || localStorage.getItem('token') || '';
  } catch {
    return '';
  }
};
const headers = () => ({
  Authorization: `Bearer ${getToken()}`,
  'Content-Type': 'application/json',
});

export default function PaymentsTab() {
  const api = getApiBase();
  const [payments, setPayments] = useState([]);
  const [config, setConfig] = useState({});
  const [loading, setLoading] = useState(true);

  // Offline payment form
  const [orderId, setOrderId] = useState('');
  const [amount, setAmount] = useState('');
  const [method, setMethod] = useState('cash');

  useEffect(() => {
    Promise.all([
      fetch(`${api}/api/payments/history`, { headers: headers() }).then((r) => r.json()),
      fetch(`${api}/api/payments/config`, { headers: headers() }).then((r) => r.json()),
    ])
      .then(([hist, conf]) => {
        setPayments(hist.payments || []);
        setConfig(conf);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [api]);

  const recordPayment = async () => {
    if (!orderId || !amount) return;
    const resp = await fetch(`${api}/api/payments/record-offline`, {
      method: 'POST',
      headers: headers(),
      body: JSON.stringify({ order_id: orderId, amount: parseFloat(amount), method }),
    });
    if (resp.ok) {
      const data = await resp.json();
      setPayments((prev) => [data.payment, ...prev]);
      setOrderId('');
      setAmount('');
    }
  };

  const totalCollected = payments.reduce((sum, p) => sum + (p.amount || 0), 0);
  const methodIcons = { cash: Banknote, upi: Smartphone, card: CreditCard };

  if (loading) return <div className="p-6 text-gray-400">Loading payments...</div>;

  return (
    <div className="p-6 space-y-6">
      <h2 className="text-xl font-bold text-white flex items-center gap-2">
        <IndianRupee size={20} /> Payments
      </h2>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-gray-800 rounded-lg p-4">
          <div className="text-2xl font-bold text-green-400">
            ₹{totalCollected.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </div>
          <div className="text-sm text-gray-400">Total Collected</div>
        </div>
        <div className="bg-gray-800 rounded-lg p-4">
          <div className="text-2xl font-bold text-blue-400">{payments.length}</div>
          <div className="text-sm text-gray-400">Transactions</div>
        </div>
        <div className="bg-gray-800 rounded-lg p-4">
          <div className="text-2xl font-bold text-purple-400">
            {config.is_configured ? 'Connected' : 'Demo Mode'}
          </div>
          <div className="text-sm text-gray-400">Razorpay Status</div>
        </div>
      </div>

      {/* Record Offline Payment */}
      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-white font-semibold mb-3">Record Payment</h3>
        <div className="flex flex-wrap gap-3">
          <input
            className="bg-gray-700 text-white px-3 py-2 rounded text-sm w-40"
            placeholder="Order ID"
            value={orderId}
            onChange={(e) => setOrderId(e.target.value)}
          />
          <input
            className="bg-gray-700 text-white px-3 py-2 rounded text-sm w-32"
            placeholder="Amount (₹)"
            type="number"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
          <select
            className="bg-gray-700 text-white px-3 py-2 rounded text-sm"
            value={method}
            onChange={(e) => setMethod(e.target.value)}
          >
            <option value="cash">Cash</option>
            <option value="upi">UPI</option>
            <option value="card">Card</option>
          </select>
          <button
            className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded text-sm"
            onClick={recordPayment}
          >
            Record
          </button>
        </div>
      </div>

      {/* Payment History */}
      <div className="bg-gray-800 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-700 text-gray-300">
            <tr>
              <th className="p-3 text-left">Order</th>
              <th className="p-3 text-left">Amount</th>
              <th className="p-3 text-left">Method</th>
              <th className="p-3 text-left">Status</th>
              <th className="p-3 text-left">Time</th>
            </tr>
          </thead>
          <tbody>
            {payments.map((p, i) => (
              <tr key={i} className="border-t border-gray-700">
                <td className="p-3 text-white font-mono text-xs">{p.order_id}</td>
                <td className="p-3 text-green-400">₹{(p.amount || 0).toFixed(2)}</td>
                <td className="p-3 text-gray-300 capitalize">{p.method}</td>
                <td className="p-3">
                  <span className="px-2 py-1 rounded-full text-xs bg-green-900 text-green-300">
                    {p.status}
                  </span>
                </td>
                <td className="p-3 text-gray-400 text-xs">
                  {p.created_at ? new Date(p.created_at * 1000).toLocaleString() : '-'}
                </td>
              </tr>
            ))}
            {payments.length === 0 && (
              <tr>
                <td colSpan={5} className="p-6 text-center text-gray-500">
                  No payments recorded yet
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
