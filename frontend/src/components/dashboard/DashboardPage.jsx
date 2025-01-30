
import DisplayHoldings from "../portfolio_component/holdings";
import StatsCard from "../chart_component/StatsCard";
import TradeHistory from "../chart_component/TradeHistory";
import ChartDisplay from "../chart_component/ChartDisplay";
import "./dashboard.css";

const Dashboard = () => {
  return (
    <div className="dashboard-container">
      <div className="stats-section">
        <StatsCard title="Valid Price" value="$265.49" />
        <StatsCard title="Algo Status" value="Active" />
      </div>
      <div className="chart-section">
        <ChartDisplay />
      </div>
      <div className="holdings-section">
        <DisplayHoldings />
      </div>
      <div className="trade-history-section">
        <TradeHistory />
      </div>
    </div>
  );
};

export default Dashboard;
