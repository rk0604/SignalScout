import { useEffect, useState, useContext } from "react";
import './stockRec.css';
import PropTypes from "prop-types";
import Modal from 'react-modal';
import api from "../../api/client";

// stock related component imports 
import StockOverview from './stockOverview/overView'
import StockRisk from "./riskComponent/riskAnal";
import { StockContext } from "../StockContext";
import { terminalModalStyles } from "../modalStyles";
import SentimentAnalysis from "./sentimentAnal/SentAnal";
import StockChart from "./PriceChart/PriceChart";

Modal.setAppElement("#root");
//update this to include the pinned stocks in query and fix the sleep timer bs, check fetchPinnedStocks
export function Recommendations() {
  const { setPinnedStocks } = useContext(StockContext); //access the context of the pinned stocks
  const [modalIsOpen, setModalIsOpen] = useState(false);
  const [selectedStock, setSelectedStock] = useState("");
  const [recommendations, setRecommendations] = useState([]); // ordered, highest indicator first
  const [isLoading, setIsLoading] = useState(false); // track the loading state
  const [snapshotRef, setSnapshotRef] = useState(null); // id of the market data these ratings came from
  const [isCached, setIsCached] = useState(false); // whether the result was served from a snapshot
  const [holdingsUpdate, setHoldingsUpdate] = useState({ // used when the user inputs their holding of a stock
    ticker:'',
    price:'',
    num_shares:'',
  })


// ------------------------------------------------------------ Main functions (backend interactions) --------------------------------------------------------------------------

  // used to fetch the top 20 stock recs
  const fetchRecs = async()=>{
    setIsLoading(true); // start spinner
    try{
      console.log('fetching recs')
      const response = await api.post('/fetch-recs', {});

      if(response.status === 200){
        // The backend returns {recommendations, snapshot_ref, cached}; snapshot_ref
        // identifies the exact market data these ratings were derived from.
        setRecommendations(response.data.recommendations || [])
        setSnapshotRef(response.data.snapshot_ref || null)
        setIsCached(Boolean(response.data.cached))
      }

    }catch(err){
      const {response} = err;
      if(response){
        switch(response.status){
          case 429:
            console.warn('rate limited by the market data provider; try again shortly');
            alert('Market data provider is rate limiting us. Try again in a few minutes.');
            break;
          case 503:
            console.warn('no recommendation data available right now');
            break;
          default:
            console.log('internal server error')
        }
      }else{
        console.log(err)
      }
    }finally{
      setIsLoading(false) // always stop the spinner, success or failure
    }
  }

  //update holdings for a stock
  const updateHoldings = async(e) =>{
    e.preventDefault() // prevent page reload
    try{
      const response = await api.post('/update-holdings', { holdingsUpdate });

      if(response.status === 200){
        console.log('response: ',response.data)
        setPinnedStocks((prev) => [...(prev || []), response.data.data.ticker]);
      }

    }catch(err){
      const {response} = err;
      if(response){
        switch(response.status){
          case 400:
            console.log('not enough shares to sell')
            break;
          default:
            console.warn('internal server error');
            break;
        }
      } else{
        console.log('err: ', err)
      }
    }
  }

//-------------------------------------------------------------- Helper functions ---------------------------------------------------------------------------------------

  // Corrected function to set the selected stock
  const chosenStock = (stock) => {
    setSelectedStock(stock);
    setModalIsOpen(true);
    setHoldingsUpdate(prevState => ({
      ...prevState,
      ticker: stock
    }));
  };

  // handles the useState hook update for holdings
  const handleHoldingsFormUpdate = (e) => {
    setHoldingsUpdate(prevState => ({
        ...prevState,
        [e.target.name]: e.target.value
    }));
  };


  //main useEffect hook
  useEffect(() => {
    const timer = setTimeout(() => {
    // fetchRecs();
    }, 500); // Delay execution to prevent rapid calls

    return () => clearTimeout(timer);
  }, []);
  

  return (
    <div className="recommend-card">
      <h3 className="recommend-title" onClick={()=>{fetchRecs()}} >Recommendations</h3>
      {snapshotRef && (
        <p className="recommend-provenance ibm-plex-sans-medium" title={`Market data snapshot ${snapshotRef}`}>
          {isCached ? 'cached snapshot' : 'fresh snapshot'} · {snapshotRef.slice(0, 8)}
        </p>
      )}
      <div className="recommend-grid">
      {isLoading ? (
          <h3 className="loading-text">Loading stock recommendations</h3>
        ) : (
          // An ordered array, so the backend's ranking by indicator is preserved.
          recommendations.map((rec) => (
            <RecContainer
              key={rec.ticker}
              stock={rec.ticker}
              rating={rec.rating}
              indicator={rec.indicator}
              onClick={chosenStock}
            />
          ))
        )}
        <Modal 
          isOpen={modalIsOpen}
          onRequestClose={() => {
            setSelectedStock("");
            setModalIsOpen(false)
          }}
          contentLabel={`${selectedStock} Analysis`}
          style={terminalModalStyles}
        >
          <h2 className="stock-year">Ticker: {selectedStock}</h2>

          <div className="stock-content">
            <StockChart stock={selectedStock}/>
          </div>

          <div className="stock-content">
            <StockOverview stock={selectedStock}/>
          </div>

          <div className="stock-content">
            <StockRisk stock={selectedStock}/>
          </div>

          <div className="stock-content">
            <SentimentAnalysis stock={selectedStock} />
          </div>


          <div className="stock-content">
          <form className="stock-holding-form" onChange={handleHoldingsFormUpdate} onSubmit={updateHoldings}>
              <label className="stock-holding-form-label ibm-plex-sans-medium">
                  Ticker:
                  <input 
                    type="text" 
                    className="stock-holding-form-input ibm-plex-sans-medium" 
                    value={holdingsUpdate.ticker} 
                    name="ticker" 
                    onChange={handleHoldingsFormUpdate} // Added onChange
                    required 
                  />
              </label>
              <label className="stock-holding-form-label ibm-plex-sans-medium">
                  Transaction Price:
                  <input 
                    type="number" 
                    className="stock-holding-form-input ibm-plex-sans-medium" 
                    name="price"    
                    value={holdingsUpdate.price}  
                    onChange={handleHoldingsFormUpdate} // Added onChange
                    required 
                  />
              </label>

              <label className="stock-holding-form-label ibm-plex-sans-medium">
                  Number of Shares in Transaction:
                  <p className="ibm-plex-sans" style={{color:'#FFFFFF'}}>*negative if sell order*</p>
                  <input 
                    type="number" 
                    className="stock-holding-form-input ibm-plex-sans-medium" 
                    value={holdingsUpdate.num_shares} 
                    name="num_shares" 
                    onChange={handleHoldingsFormUpdate} // Added onChange
                    required 
                  />
              </label>
              <button type="submit" className="ibm-plex-sans-medium">Update Holdings</button>
          </form>
          </div>

          <button onClick={() => {
            setSelectedStock("");
            setModalIsOpen(false)
          }}
          className="close-btn ibm-plex-sans-medium"
          >
            Close
          </button>
        </Modal>
      </div>
    </div>
  );
}

// ----------------------------------------------------------- stock rec component -----------------------------------------------------------

const RecContainer = ({ stock, rating, indicator, onClick }) => {
  // Determine if rating should be upgraded based on indicator value
  const adjustedRating = (() => {
    if (rating.toLowerCase() === "buy" && indicator > 0.85) return "strong buy";
    if (rating.toLowerCase() === "sell" && indicator > 0.85) return "strong sell";
    return rating.toLowerCase();
  })();

  // Color mappings based on adjusted rating
  const getColor = () => {
    switch (adjustedRating) {
      case "strong buy": return "#7CFC00";  
      case "buy": return "#0BDA51";       
      case "hold": return "#2196F3";       
      case "sell": return "#FA5F55";     
      case "strong sell": return "#D2042D"; 
      default: return "#FFFFFF";           
    }
  };

  return (
    <div 
      className="rec-container" 
      style={{ 
        borderColor: getColor(), 
        color: getColor(), 
        boxShadow: adjustedRating === "strong buy" ? "0px 0px 3px #7CFC00" : 
                   adjustedRating === "strong sell" ? "0px 0px 3px #D2042D" :
                   "0px 0px 0px rgba(255, 255, 255, 0.5)"
      }}
      onClick={() => onClick(stock)}  // Now properly passing stock name
    >
      <h2>{stock}</h2>
      <p>{adjustedRating}</p>
    </div>
  );
};

// PropTypes validation
RecContainer.propTypes = {
  stock: PropTypes.string.isRequired,
  rating: PropTypes.string.isRequired,
  indicator: PropTypes.number.isRequired,
  onClick: PropTypes.func.isRequired
};

export default RecContainer;

// -------------------------------------------------------- stock chart ---------------------------------------------------------------------------------------

const StockHistoricalChart = ({stock}) =>{

  return(
    <div className="stock-chart">
      <h2>{stock}</h2>
      <p>Stock Chart</p>
    </div>
  );
}

StockHistoricalChart.propTypes = {
  stock: PropTypes.string.isRequired
}

