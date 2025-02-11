
import DisplayHoldings from "../portfolio_component/holdings";
import QueryStock from "../chart_component/QueryStock";
import { Recommendations } from "../chart_component/stock_rec";
import ReuseCard from "../chart_component/ui_component";
import "./dashboard.css";

const Dashboard = () => {
  return (
    <div className="dashboard-container">
      <div className="chart-section">
        <ReuseCard>
          <Recommendations/>
        </ReuseCard>
      </div>
      <div className="holdings-section">
        <ReuseCard>
          <DisplayHoldings />
        </ReuseCard>
      </div>
      <div className="trade-history-section">
        <ReuseCard>
          <QueryStock/>
        </ReuseCard>
      </div>
    </div>
  );
};

export default Dashboard;
