
import DisplayHoldings from "../portfolio_component/holdings";
import PortfolioSummary from "../portfolio_component/PortfolioSummary";
import BacktestPanel from "../backtest_component/BacktestPanel";
import AgentPanel from "../agent_component/AgentPanel";
import QueryStock from "../chart_component/QueryStock";
import { Recommendations } from "../chart_component/stock_rec";
import ReuseCard from "../chart_component/ui_component";
import "./dashboard.css";

const Dashboard = () => {
  return (
    <div className="dashboard-container">
      <div className="portfolio-section">
        <PortfolioSummary />
      </div>
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
      <div className="agent-section">
        <AgentPanel />
      </div>
      <div className="backtest-section">
        <BacktestPanel />
      </div>
    </div>
  );
};

export default Dashboard;
