import React, { useState, useEffect } from 'react';
import { Users, Clock, Award, AlertTriangle } from 'lucide-react';

const getApiBase = () => (typeof window !== 'undefined' ? window.location.origin : '');
const getToken = () => {
  try {
    return localStorage.getItem('retailos_token') || localStorage.getItem('token') || '';
  } catch {
    return '';
  }
};

export default function StaffTab() {
  const api = getApiBase();
  const [staff, setStaff] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${api}/api/v2/staff`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
      .then((r) => r.json())
      .then((data) => setStaff(data.staff || []))
      .catch(() => setStaff([]))
      .finally(() => setLoading(false));
  }, [api]);

  if (loading) return <div className="p-6 text-gray-400">Loading staff...</div>;

  return (
    <div className="p-6 space-y-6">
      <h2 className="text-xl font-bold text-white flex items-center gap-2">
        <Users size={20} /> Staff Management
      </h2>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-gray-800 rounded-lg p-4">
          <div className="text-2xl font-bold text-blue-400">{staff.length}</div>
          <div className="text-sm text-gray-400">Total Staff</div>
        </div>
        <div className="bg-gray-800 rounded-lg p-4">
          <div className="text-2xl font-bold text-green-400">
            {staff.filter((s) => s.is_active).length}
          </div>
          <div className="text-sm text-gray-400">Active</div>
        </div>
        <div className="bg-gray-800 rounded-lg p-4">
          <div className="text-2xl font-bold text-yellow-400">
            {staff.filter((s) => s.current_shift).length}
          </div>
          <div className="text-sm text-gray-400">Currently on Shift</div>
        </div>
      </div>

      <div className="bg-gray-800 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-700 text-gray-300">
            <tr>
              <th className="p-3 text-left">Name</th>
              <th className="p-3 text-left">Role</th>
              <th className="p-3 text-left">Phone</th>
              <th className="p-3 text-left">Status</th>
            </tr>
          </thead>
          <tbody>
            {staff.map((s, i) => (
              <tr key={i} className="border-t border-gray-700">
                <td className="p-3 text-white">{s.name || s.full_name}</td>
                <td className="p-3 text-gray-300">{s.role}</td>
                <td className="p-3 text-gray-400">{s.phone}</td>
                <td className="p-3">
                  <span
                    className={`px-2 py-1 rounded-full text-xs ${
                      s.is_active ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'
                    }`}
                  >
                    {s.is_active ? 'Active' : 'Inactive'}
                  </span>
                </td>
              </tr>
            ))}
            {staff.length === 0 && (
              <tr>
                <td colSpan={4} className="p-6 text-center text-gray-500">
                  No staff members found
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
