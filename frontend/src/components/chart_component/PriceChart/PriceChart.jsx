import { useEffect, useState } from "react";
import PropTypes from "prop-types";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
  ReferenceDot
} from "recharts";
import "./price.css";
import api from "../../../api/client";

const UP = "#16C784";
const DOWN = "#EA3943";

const StockChart = ({ stock }) => {
  const [series, setSeries] = useState([]);   // date/price/ma20/ma50 points
  const [signals, setSignals] = useState([]); // MA20/50 crossover points
  const [error, setError] = useState(null);

  // Read the ticker from props rather than copying it into state: state
  // initialisers only run on mount, so a copy would keep showing the first
  // ticker when the modal is reopened for a different one.
  useEffect(() => {
    if (!stock) return;

    const fetchStockData = async () => {
      try {
        const response = await api.get("/get-chart-data", {
          params: { stock },
        });

        // Backend returns {ticker, series, signals, signal_strategy}
        setSeries(response.data.series || []);
        setSignals(response.data.signals || []);
        setError(null);
      } catch (err) {
        setError(err.response?.data?.error || "Failed to fetch data");
        setSeries([]);
        setSignals([]);
      }
    };

    fetchStockData();
  }, [stock]);

  const latestSignal = signals.length ? signals[signals.length - 1] : null;

  return (
    <div className="price-chart-container">
      {error ? (
        <p style={{ color: "red" }}>{error}</p>
      ) : (
        <>
          {/* Most recent crossover, stated in words so the chart marker is unambiguous */}
          {latestSignal && (
            <p className="signal-callout ibm-plex-sans-medium">
              <span style={{ color: latestSignal.signal === "Buy" ? UP : DOWN }}>
                {latestSignal.signal === "Buy" ? "▲ Golden cross" : "▼ Death cross"}
              </span>
              {" "}on {latestSignal.date} — MA20 crossed{" "}
              {latestSignal.signal === "Buy" ? "above" : "below"} MA50
            </p>
          )}

          <ResponsiveContainer width="100%" height={400}>
            <LineChart data={series} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>

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

              <Tooltip
                contentStyle={{ backgroundColor: "#1e1e1e", borderColor: "#ffcc00", color: "#fff" }}
                formatter={(value, name) => [
                  value == null ? "—" : `$${Number(value).toFixed(2)}`,
                  name,
                ]}
              />

              <Legend wrapperStyle={{ fontSize: 12, color: "#ccc" }} />

              <Line
                type="basis"
                dataKey="price"
                name="Price"
                stroke="url(#lineGradient)"
                strokeWidth={2.5}
                dot={false}
              />

              {/* Moving averages: thinner and dashed so price stays the focus.
                  connectNulls={false} leaves a gap during the warmup period
                  rather than drawing a misleading line from zero. */}
              <Line
                type="monotone"
                dataKey="ma20"
                name="MA20"
                stroke="#35B7F3"
                strokeWidth={1.5}
                strokeDasharray="4 3"
                dot={false}
                connectNulls={false}
              />
              <Line
                type="monotone"
                dataKey="ma50"
                name="MA50"
                stroke="#A78BFA"
                strokeWidth={1.5}
                strokeDasharray="4 3"
                dot={false}
                connectNulls={false}
              />

              {/* Crossover markers sit on the price line at the signal date */}
              {signals.map((s) => (
                <ReferenceDot
                  key={`${s.date}-${s.signal}`}
                  x={s.date}
                  y={s.price}
                  r={6}
                  fill={s.signal === "Buy" ? UP : DOWN}
                  stroke="#0A0A0A"
                  strokeWidth={2}
                  isFront
                />
              ))}
            </LineChart>
          </ResponsiveContainer>

          {signals.length === 0 && series.length > 0 && (
            <p className="signal-callout ibm-plex-sans-medium" style={{ color: "#8A929E" }}>
              No MA20/50 crossovers in the last year
            </p>
          )}
        </>
      )}
    </div>
  );
};

StockChart.propTypes = {
  stock: PropTypes.string,
};

export default StockChart;
