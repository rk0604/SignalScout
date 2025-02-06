import PropTypes from "prop-types";
import './chartComponent.css';

function StatsCard({ title, value }) {
  return (
    <div className="stats-card">
      <h3>Stats</h3>
      <p className="stats-title">{title}</p>
      <p className="stats-value">{value}</p>
    </div>
  );
};

StatsCard.prototype= {
    title: PropTypes.string,
    value: PropTypes.string
}

export default StatsCard;



