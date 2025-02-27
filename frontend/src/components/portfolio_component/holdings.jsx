import axios from 'axios';
import "./holdings.css";
import { useState, useEffect } from 'react';
import Modal from 'react-modal'

Modal.setAppElement("#root");

export function DisplayHoldings(){
    /**
     * 1. Helps a user keep track of all their holdings
     * 2. Fetches the user's holdings from the backend every 5 seconds, as a CRON job
     * 3. Displays the user's holdings in a table
     */
    const [holdings, setHoldings] = useState([]); // holds the user's holdings, and gets updated when user buys/sells a stock
    const [userEmail, setUserEmail] = useState('') // holds the user email fetched from the localstorage, needed for querying
    const [modalIsOpen, setModalIsOpen] = useState(false);
    const [selectedHolding, setSelectedHolding] = useState("") //should be a sticker
// ------------------------------------------------ Functions -------------------------------------------------------------------------------------------------------
    
    const API_URL = import.meta.env.VITE_API_URL;

    // used to fetch the user's holdings from the backend
    const fetchHoldings = async () => {
        if (!userEmail) {
            console.log('Invalid credentials for fetching user holdings');
            return;
        }
        try {
            const response = await axios.get(`${API_URL}/get-holdings`, {
                params: { userEmail }, 
                withCredentials: true, 
                headers: {
                    'Accept': 'application/json',
                }
            });
    
            if (response.status === 200) {
                console.log(response.data.holdings);
                setHoldings(response.data.holdings);
            }
        } catch (err) {
            const { response } = err;
            if (response) {
                switch (response.status) {
                    case 400:
                        console.log('invalid credentials')
                        alert('invalid credentials')
                        break;
                    case 401:
                        console.log('Unauthorized');
                        alert('Unauthorized');
                        break;
                    case 500:
                        console.log('Internal server error');
                        alert('Internal server error');
                        break;
                    default:
                        console.log('Unknown error');
                        break;
                }
            } else {
                console.log(err);
            }
        }
    };
    // Corrected function to set the selected stock
  const chosenStock = (stock) => {
    setSelectedHolding(stock);
    setModalIsOpen(true);
  };

// --------------------------------------------------- Use effect hooks ------------------------------------------------------------------------------------------------
    useEffect(() => {
        const userEmail = localStorage.getItem('email')
        setUserEmail(userEmail)
        // const timer = setTimeout(() => {
        //     fetchHoldings();
        //   }, 500); // Delay execution to prevent rapid calls
        //   return () => clearTimeout(timer);
    },[]);

    return(
        <div className="holdings-container">
            <div className="holdings-card">
                <div className="holdings-header">
                    <h3 className='ibm-plex-sans-medium'>Your Holdings</h3>
                    <button className="refreshButton ibm-plex-sans-medium" onClick={()=>{fetchHoldings()}} >Refresh Holdings</button>
                </div>

                {holdings.length > 0 ? (
                    <div className="holdings-grid">
                        {holdings.map((holding, index) => (
                            <div key={index} className="holding-item" onClick={()=>{chosenStock(holding.ticker)}} >
                                <h2 className="holding-name ibm-plex-sans-heavy-ov"><u>({holding.ticker})</u></h2>
                                <p><span className="holding-value ibm-plex-sans-medium">Shares: </span>{holding.num_shares}</p>
                                <p><span className="holding-value ibm-plex-sans-medium">Average Price: </span>${holding.avg_price}</p>
                                <p><span className="holding-value ibm-plex-sans-medium" style={{color: '#0BDA51'}} >Value of Holding: </span>${holding.value.toLocaleString()}</p>
                                <p><span className="holding-value ibm-plex-sans-medium">% Return On Investment (ROI): </span>{holding.total_return.toFixed(2)}%</p>
                            </div>
                        ))}
                        <Modal 
                                isOpen={modalIsOpen}
                              onRequestClose={() => {
                                setSelectedHolding("");
                                setModalIsOpen(false);
                                }}
                              contentLabel={`${selectedHolding} Analysis`}
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
                               <h1>Stock {selectedHolding}</h1>
                               <h3>Show a sentiment analysis***</h3>
                               <h3>Show a stock price chart</h3>

                               <button 
                                onClick={() => {
                                    setSelectedHolding("");
                                    setModalIsOpen(false)
                                    }}
                                className="close-btn ibm-plex-sans-medium">
                                Close
                                </button>
                            </Modal> 
                    </div>
                ) : (
                    <div className="no-holdings">
                        <h4>Buy something first, broke ass</h4>
                    </div>
                )}
            </div>
        </div>
    )
}

export default DisplayHoldings;




