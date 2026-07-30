import { useState, useContext } from 'react';
import './query.css';
import Modal from 'react-modal';
import StockOverview from './stockOverview/overView';
import { StockContext } from '../StockContext';
import api from '../../api/client';

Modal.setAppElement("#root");

// This component allows a user to search for a specific stock and get its analysis 
const QueryStock = () => {
  const { pinnedStocks, setPinnedStocks } = useContext(StockContext); //access the context of the pinned stocks
  const [isPinned, setIsPinned] = useState(false); // indicates if a queried stock is already pinned or not?

  const [query, setQuery] = useState(''); // Holds the ticker of the stock to be queried
  const [modalIsOpen, setModalIsOpen] = useState(false); // Manages the closed/open state of the modal 
  const [stockTicker, setStockTicker] = useState(''); // Holds the stock ticker for display
  const [selectedStock, setSelectedStock] = useState(null); // Holds selected stock for analysis

  // ----------------------------------------------Helper Functions------------------------------------------------------------------------

  // Handles the query submission event  
  const handleSubmit = (event) => {
    event.preventDefault();
    if (query.trim() !== "") {
      setStockTicker(query.toUpperCase());
  
      let found = pinnedStocks.filter((stockObj) => {
        return stockObj.toUpperCase() === query.toUpperCase();
      });
  
      if (found.length === 0) {
        setIsPinned(false);
      } else {
        setIsPinned(true);
      }
    }
  };
  

  // Handles the change in the form input
  const handleChange = (event) => {
    setQuery(event.target.value);
  };

  //sends the query hook to the backend and a new entry is created. 
  const handlePin = async() =>{
    if(!query || query === ''){ 
      console.log('cannot pin an empty stock, query: ', query);
      return;
    }

    //query the pinnedStocks to see 
    let found = pinnedStocks.filter((stockObj) => {
      return stockObj.toUpperCase() === query.toUpperCase();
    });

    if (found.length !== 0) {
      //stock is already pinned
      console.log('stock already pinned, now removing it')
      return
    }

    try{
      const response = await api.post('/pin-stock', { query });

      if(response.status === 200){
        // console.log('response: ',response.data)
        setPinnedStocks((prev) => [...(prev || []), response.data.data]); // append the new stock to the previous list
        setIsPinned(true)
      }

    }catch(err){
      const {response} = err;
      switch(response?.status){
        case 400:
          console.log("ticker is required");
          break;
        case 401:
          console.log('holding exists already, and is pinned');
          break;
        default:
          console.log('internal server error');
          break;
      }
    }
  }

  //sets the pinned attribute in DB entry to false
  // early exit if user has holdings, DONT let user unpin a stock they own share sin 
  const handleRemovePin = async() =>{
    if(!query || query === ''){ 
      console.log('invalid query')
      return
    }

    try{
      const response = await api.get('/remove-pinned-stock', {
        params: { query: query },
      });

      if(response.status === 200){
        console.log('response: ', response.data)
        let removedStock = pinnedStocks.filter(tick => tick !== query);
        setPinnedStocks(removedStock);

        if(isPinned === true){
          setIsPinned(false)
        }
      }
    }catch(err){
      const {response} = err;
      switch(response?.status){
        case 400:
          console.log('invalid query or credentials')
          break;
        case 401:
          console.log('cannot unpin a stock that you are actively holding shares in')
          alert('cannot unpin a stock that you are actively holding shares in')
          break;
        default:
          console.warn('internal server error');
          break;
      }
    }
  }

  return (
    <div className="query-stock-card ibm-plex-sans-medium">
        <div className="group-query-stock">
          <h3 style={{ paddingBottom: '4px', textAlign: 'center' }}>Search a specific stock</h3>
          <form onSubmit={handleSubmit}>
            <input 
              placeholder="Search a Stock by its ticker" 
              type="search" 
              className="input ibm-plex-sans-medium" 
              style={{ marginBottom: '4px' }}
              onChange={handleChange} 
              value={query}
            />
          </form>
        </div>

        {/* Displays queried stock information */}
        {stockTicker && (
          <div className='stock-query-info' onClick={() => {
            setSelectedStock(stockTicker);
            setModalIsOpen(true);
          }}>
            <h2 className="holding-name ibm-plex-sans-heavy-ov"><u>{stockTicker}</u></h2>
            <button
              className="pin-stock"
              onClick={(e) => {
                e.stopPropagation();
                handlePin();
              }}
              style={{
                borderColor: isPinned ? "#0BDA51" : "#ffcc00",
                boxShadow: isPinned ? "0 0 3px 1px #0BDA51" : "none",
              }}
            >
              📌
            </button>

            <button
              className="unpin-stock"
              onClick={(e) => {
                e.stopPropagation();
                handleRemovePin();
              }}
              style={{
                borderColor: isPinned ? "rgb(218, 11, 11)" : "#ffcc00",
                boxShadow: isPinned ? "0 0 3px 1px rgb(218, 11, 11)" : "none",
              }}
            >
              ❌
            </button>
          </div>
        )}

        {/* Stock Analysis Modal */}
        <Modal 
          isOpen={modalIsOpen}
          onRequestClose={() => {
            setModalIsOpen(false);
          }}
          shouldCloseOnOverlayClick={true} // Allows clicking outside to close the modal
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
          {/* Ensure StockOverview only renders if a stock is selected */}
          {selectedStock && <StockOverview stock={selectedStock} />}

          <button 
            onClick={() => {
              setModalIsOpen(false);
            }}
            className="close-btn ibm-plex-sans-medium">
            Close
          </button>
        </Modal>
    </div>
  );
};

export default QueryStock;
