import React, { useEffect, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid
} from "recharts";
import "./price.css";

const StockChart = ({ stock }) => {
  const API_URL = import.meta.env.VITE_API_URL;
  const [data, setData] = useState([]);
  const [error, setError] = useState(null);
  const [selectedStock, setSelectedStock] = useState(stock || "");

  useEffect(() => {
    if (!selectedStock) return;

    const fetchStockData = async () => {
      try {
        const response = await fetch(`${API_URL}/get-chart-data?stock=${selectedStock}`, {
          credentials: "include",
          headers: { Accept: "application/json" },
        });

        const result = await response.json();

        if (response.ok) {
          setData(result);
          setError(null);
        } else {
          setError(result.error || "Unknown error");
          setData([]);
        }
      } catch (err) {
        setError("Failed to fetch data");
        setData([]);
      }
    };

    fetchStockData();
  }, [selectedStock]);

  return (
    <div className="price-chart-container">
      {error ? (
        <p style={{ color: "red" }}>{error}</p>
      ) : (
        <ResponsiveContainer width="100%" height={400}>
          <LineChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
            
            {/* ✅ FIX: Use Native SVG Elements Instead of Importing `defs` */}
            <defs>
              <linearGradient id="lineGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#ffcc00" stopOpacity={0.8} />
                <stop offset="95%" stopColor="#ffcc00" stopOpacity={0.4} />
              </linearGradient>
            </defs>

            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />

            <XAxis 
              dataKey="date" 
              tick={{ fontSize: 12, fill: "#ccc" }}
              tickMargin={10}
              angle={-15}
              textAnchor="end"
            />

            <YAxis 
              domain={["auto", "auto"]} 
              tick={{ fontSize: 12, fill: "#ccc" }} 
            />

            <Tooltip contentStyle={{ backgroundColor: "#1e1e1e", borderColor: "#ffcc00", color: "#fff" }} />

            <Line 
              type="basis"
              dataKey="price"
              stroke="url(#lineGradient)"
              strokeWidth={2.5}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
};

export default StockChart;
