// dashboard/src/Scheduling.jsx
import React, { useState, useEffect } from 'react';

const Scheduling = () => {
  const [scheduleData, setScheduleData] = useState(null);

  useEffect(() => {
    // In production, this pulls the structured AI report natively from the approval queue APIs
    setScheduleData({
      date: "Saturday 14 Dec",
      predicted_footfall: 340,
      increase_pct: 18,
      reason: "Proximity to year-end + local market day",
      hourly_blocks: [
        { time: "10am-12pm", status: "Adequate", staff: 2, limit: "~30 customers/hr" },
        { time: "12pm-2pm", status: "Understaffed", staff: 2, limit: "~55 customers/hr" },
        { time: "4pm-7pm", status: "Understaffed", staff: 3, limit: "~70 customers/hr" },
        { time: "7pm-9pm", status: "Adequate", staff: 2, limit: "~25 customers/hr" }
      ],
      recommendation: "Add 1 staff member 12pm-2pm. Add 2 staff members 4pm-7pm."
    });
  }, []);

  if (!scheduleData) return <div>Loading Schedule...</div>;

  return (
    <div className="scheduling-dashboard p-6 bg-white rounded shadow text-gray-800">
      <h2 className="text-2xl font-bold mb-4">Tomorrow — {scheduleData.date}</h2>
      
      <div className="metrics bg-blue-50 p-4 rounded mb-6">
        <p><strong>Predicted footfall:</strong> {scheduleData.predicted_footfall} customers <span className="text-red-500 font-bold">({scheduleData.increase_pct}% above normal)</span></p>
        <p><strong>Reason:</strong> {scheduleData.reason}</p>
      </div>

      <h3 className="text-xl font-semibold mb-2">Hour-by-hour adequacy:</h3>
      <ul className="list-none space-y-2 mb-6">
        {scheduleData.hourly_blocks.map((block, i) => (
          <li key={i} className="flex gap-4">
            <span className="w-24 text-right font-medium">{block.time}</span>
            <span className={`w-32 ${block.status === "Adequate" ? "text-green-600" : "text-red-600 font-bold"}`}>
              {block.status === "Adequate" ? "✓" : "✗"} {block.status}
            </span>
            <span className="text-gray-600">({block.staff} staff, {block.limit})</span>
          </li>
        ))}
      </ul>

      <div className="recommendation border-t pt-4">
        <h3 className="text-xl font-semibold mb-2">Recommendation:</h3>
        <p className="whitespace-pre-wrap">{scheduleData.recommendation}</p>
      </div>
    </div>
  );
};

export default Scheduling;
