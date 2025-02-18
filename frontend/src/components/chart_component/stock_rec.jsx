import { useEffect, useState } from "react";
import './stockRec.css';
import PropTypes from "prop-types";
import Modal from 'react-modal';
import axios from "axios";

// stock related component imports 
import StockOverview from './stockOverview/overView'
import StockRisk from "./riskComponent/riskAnal";

Modal.setAppElement("#root");

export function Recommendations() {
  const [modalIsOpen, setModalIsOpen] = useState(false);
  const API_URL = import.meta.env.VITE_API_URL;
  const [selectedStock, setSelectedStock] = useState("");
  const [recommendations, setRecommendations] = useState([]); 
  const [holdingsUpdate, setHoldingsUpdate] = useState({
    ticker:'',
    price:'',
    num_shares:'',
  })
  const [email, setEmail] = useState('');


// ------------------------------------------------------------ Main functions (backend interactions) --------------------------------------------------------------------------

  // used to fetch the top 20 stock recs
  const fetchRecs = async()=>{
    try{
      console.log('fetching recs')
      const response = await axios.post(`${API_URL}/fetch-recs`, {
        withCredentials: true,
        headers:{  "Content-Type": "application/json"}
      });

      if(response.status){
        console.log(response.data);
        setRecommendations(response.data)
      }

    }catch(err){
      const {response} = err;
      if(response){
        switch(response.status){
          case 400:
            console.log('could not fetch the ');
            break;
          default:
            console.log('internal server error')
        }
      }else{
        console.log(err)
      }
    }
  }

  //update holdings for a stock
  const updateHoldings = async(e) =>{
    e.preventDefault() // prevent page reload
    const payload = {email, holdingsUpdate}
    try{
      const response = await axios.post(`${API_URL}/update-holdings`, payload,{
        withCredentials:true,
        headers:{  "Content-Type": "application/json"}
      });

      if(response.status === 200){
        console.log('response: ',response.data)
      }

    }catch(err){
      const {response} = err;
      if(response){
        switch(response.status){
          case 400:
            console.log('invalid details')
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
    setEmail(localStorage.getItem('email'))
    const timer = setTimeout(() => {
      fetchRecs();
    }, 500); // Delay execution to prevent rapid calls
  
    return () => clearTimeout(timer); // Cleanup previous timeout
  }, []);  

  return (
    <div className="recommend-card">
      <h3 className="recommend-title">Recommendations</h3>
      <div className="recommend-grid">
      {recommendations ?
      (
        Object.entries(recommendations).map(([stock, data]) => (
        <RecContainer 
          key={stock} 
          stock={stock} 
          rating={data.rating} 
          indicator={data.indicator}
          onClick={chosenStock}
        />
        ))
    ):
      <p className="loading-text">Loading stock recommendations</p>
      
      }

        <Modal 
          isOpen={modalIsOpen}
          onRequestClose={() => {
            setSelectedStock("");
            setModalIsOpen(false)
          }}
          contentLabel={`${selectedStock} Analysis`}
          style={{
            overlay: { backgroundColor: "rgba(0, 0, 0, 0.75)" },
            content: {
              color: "white",
              background: "#1a1a1a",
              borderRadius: "10px",
              padding: "20px",
              maxWidth: "80vw",
              margin: "auto",
              textAlign: "center",
              overflowY: "auto",
            },
          }}
        >
          <h2 className="stock-year">Ticker: {selectedStock}</h2>

          <div className="stock-content">
            <StockOverview stock={selectedStock}/>
          </div>

          <div className="stock-content">
            <StockRisk stock={selectedStock}/>
          </div>

          <div className="stock-content">
            {/* <StockHistoricalChart stock={selectedStock}/> */}
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
                  Buy Price:
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
                  Number of Shares Bought:
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

