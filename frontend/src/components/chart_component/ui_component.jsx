import './chartComponent.css';
import PropTypes from 'prop-types';

const ReuseCard = ({ children }) => {
  return (
    <div className="reuse-card">
      <div className="reuse-placeholder">
        {children}  {/* This will render whatever component is passed */}
      </div>
    </div>
  );
};

ReuseCard.propTypes = {
  children: PropTypes.node, //maybe set to required
};

export default ReuseCard;

export const LoadingWheel = () =>{
  return(
<div className="container-loading-wheel">
  <span></span>
  <span></span>
  <span></span>
  <span></span>
</div>
  )
}
