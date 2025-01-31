
// import DisplayHoldings from "../portfolio_component/holdings";
// import StatsCard from "../chart_component/StatsCard";
import TradeHistory from "../chart_component/TradeHistory";
import ReuseCard from "../chart_component/ui_component";
import "./dashboard.css";

const Dashboard = () => {
  return (
    <div className="dashboard-container">
      <div className="stats-section">
        <ReuseCard>
          
        </ReuseCard>
      </div>
      <div className="chart-section">
        <ReuseCard>
          
        </ReuseCard>
      </div>
      <div className="holdings-section">
        <ReuseCard>
          
        </ReuseCard>
      </div>
      <div className="trade-history-section">
        <ReuseCard>
          <TradeHistory/>
        </ReuseCard>
      </div>
    </div>
  );
};

export default Dashboard;
