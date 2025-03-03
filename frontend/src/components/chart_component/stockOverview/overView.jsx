import './overview.css'
import PropTypes from 'prop-types';
import { useEffect, useState } from 'react';
import axios from 'axios';

// used to display the basic financial data for a stock
export const StockOverview = ({ stock }) => {
  const API_URL = import.meta.env.VITE_API_URL;
  const [stockData, setStockData] = useState(null); // holds the stock data
  const [userPinnedStocks, setPinnedaStocks] = useState([]); // holds the set of stocks the user has pinned 

  // Fetch stock details from Flask backend using yfinance API
  const fetchStockDetails = async () => {
    if (!stock) return;
    const stockToSend = { ticker: stock.toUpperCase() };
    console.log('fetching stock details: ', stock)

    try {
      const response = await axios.post(`${API_URL}/fetch-stock-data`, stockToSend, {
        withCredentials: true,
        headers: {
          "Content-Type": "application/json",
        },
      });
      // console.log("📥 Raw API Response:", response.data);
      if (response.status === 200 && response.data?.financials) {
        let financials = response.data.financials;
  
        if (typeof financials === "string") {
          try {
            financials = JSON.parse(financials);
          } catch (error) {
            console.error("🚨 Failed to parse financials JSON:", error);
          }
        }        
        // console.log("✅ Parsed Financials:", financials);
  
        setStockData({ ...response.data, financials });
      } else {
        console.error("⚠️ No financial data received:", response.data);
      }
    } catch (err) {
      const {response} = err;
      if(response){
        switch(response.status){
          case 400: 
            console.log('invalid request');
            break;
          case 404: 
            console.log('❌ financial data is unavailable at this moment');
            break;
          default:
            console.error("❌ Error fetching stock data:", err); 
        }

      } else{
        console.error("❌ Error fetching stock data:", err); 
      }
    }
  };
  

  // Fetch stock details on mount or when the stock changes
  useEffect(() => {
    const timer = setTimeout(() => {
      fetchStockDetails();
    }, 500); // Delay execution to prevent rapid calls
  
    return () => clearTimeout(timer); // Cleanup previous timeout
  }, [stock]);  

  // Extract financials
  const financials = stockData?.financials || {};
  const latestYear = Object.keys(financials).sort().pop();
  const latestData = latestYear ? financials[latestYear] : null;
  const additionalData = stockData?.additional_data || {};

  return (
    <div className="stock-overview-container ibm-plex-sans-medium">
      {latestData ? (
        <>
          <p className="stock-year">Year: {latestYear.substring(0, 4)}</p>

          <div className="stock-info-grid">
            {/* Column 1 */}
            <div className="stock-info-column" >
              <p><span className='ibm-plex-sans-heavy-ov' style={{color:'#ffcc00'}} >EBITDA:</span> ${latestData?.EBITDA ? latestData.EBITDA.toLocaleString() : "No Data"}</p>
              <p><span className='ibm-plex-sans-heavy-ov' style={{color:'#ffcc00'}} >Operating Income:</span> ${latestData["Operating Income"]?.toLocaleString() || "No Data"}</p>
              <p><span className='ibm-plex-sans-heavy-ov' style={{color:'#ffcc00'}} >Total Revenue:</span> ${latestData["Total Revenue"]?.toLocaleString() || "No Data"}</p>
              <p><span className='ibm-plex-sans-heavy-ov' style={{color:'#ffcc00'}} >Net Income:</span> ${latestData["Net Income"]?.toLocaleString() || "No Data"}</p>
            </div>

            {/* Column 2 */}
            <div className="stock-info-column">
              <p><span className='ibm-plex-sans-heavy-ov' style={{color:'#ffcc00'}} >Gross Profit:</span> ${latestData["Gross Profit"]?.toLocaleString() || "No Data"}</p>
              <p><span className='ibm-plex-sans-heavy-ov' style={{color:'#ffcc00'}} >Total Expenses:</span> ${latestData["Total Expenses"]?.toLocaleString() || "No Data"}</p>
              <p><span className='ibm-plex-sans-heavy-ov' style={{color:'#ffcc00'}} >Operating Cash Flow:</span> ${additionalData["Operating Cash Flow"]?.toLocaleString() || "No Data"}</p>
              <p><span className='ibm-plex-sans-heavy-ov' style={{color:'#ffcc00'}} >Interest Expense:</span> ${latestData["Interest Expense"]?.toLocaleString() || "No Data"}</p>
            </div>

            {/* Column 3 (New Metrics) */}
            <div className="stock-info-column">
              <p><span className='ibm-plex-sans-heavy-ov' style={{color:'#ffcc00'}} >Market Cap:</span> ${additionalData["Market Cap"]?.toLocaleString() || "No Data"}</p>
              <p><span className='ibm-plex-sans-heavy-ov' style={{color:'#ffcc00'}} >P/E Ratio:</span> {additionalData["PE Ratio"]?.toFixed(2) || "No Data"}</p>
              <p><span className='ibm-plex-sans-heavy-ov' style={{color:'#ffcc00'}} >Dividends:</span> ${additionalData["Dividends Paid"]?.toLocaleString() || "No Data"}</p>
              <p><span className='ibm-plex-sans-heavy-ov' style={{color:'#ffcc00'}} >Interest Income:</span> ${latestData["Interest Income"]?.toLocaleString() || "No Data"}</p>
            </div>

            {/* Column 4*/}
            <div className="stock-info-column">
              <p><span className='ibm-plex-sans-heavy-ov' style={{color:'#ffcc00'}} >EPS:</span> ${latestData["Basic EPS"] || "No Data"}</p>
              <p><span className='ibm-plex-sans-heavy-ov' style={{color:'#ffcc00'}} >R&D:</span> ${latestData["Research And Development"]?.toLocaleString() || "No Data"}</p>
              <p><span className='ibm-plex-sans-heavy-ov' style={{color:'#ffcc00'}} >Cost of Revenue:</span> ${latestData["Cost Of Revenue"]?.toLocaleString() || "No Data"}</p>
              <p><span className='ibm-plex-sans-heavy-ov' style={{color:'#ffcc00'}} >Latest Price:</span> ${additionalData["latest_price"]?.toFixed(2) || "No Data"}</p>
            </div>
          </div>
        </>
      ) : (
        <p className="loading-text">Loading stock data...</p>
      )}
    </div>
  );
};

StockOverview.propTypes = {
  stock: PropTypes.string.isRequired
}

export default StockOverview
