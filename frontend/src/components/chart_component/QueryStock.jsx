import { useState } from 'react';
import './query.css';
import axios from 'axios';

// this component will let a user search for a specific stock and get its analysis 
const QueryStock = () => {
  const API_URL = import.meta.env.VITE_API_URL; // 
  const [queriedStockDetails, setQueriedStockDetails] = useState(''); // holds the queried stock data
  const [query, setQuery] = useState(''); // holds the ticker of the stock to be queried


  // queries for the stock based on userInput
  const queryForStock = async() => {
    //early exit in the event of empty query
    if(query === null || query === ''){  return}

    try{
      const response = await axios.get(`${API_URL}/fetch-stock-data`, {
        params: { query }, 
        withCredentials: true, 
        headers: {
            'Accept': 'application/json',
        }
      });
  
      if(response.status === 200){
        console.log(response.data)
        setQueriedStockDetails(response.data)
      }
    }catch(err){
      const {response} = err;
      switch(response.status){
        case 400:
          console.warn('invalid query')
          break;
        case 401:
          console.warn('could not find this stock');
          break;
        default:
          console.log('internal server error');
      }
    }
  }

// ------------------------------------------------------------------------ helper functions -------------------------------------------------------------------------------
// handles the query submission event  
const handleSubmit = (event) => {
    event.preventDefault();
    if (query.trim() !== "") {
      queryForStock(query);
      setQuery(""); // Clears input after submission
    }
  }

  // handles the change in the form
  const handleChange = (event) =>{
    setQuery(event.target.value)
  }

    // Extract financials
    const financials = queriedStockDetails?.financials || {};
    const latestYear = Object.keys(financials).sort().pop();
    const latestData = latestYear ? financials[latestYear] : null;
    const additionalData = queriedStockDetails?.additional_data || {};

  return (
    <div className="query-stock-card ibm-plex-sans-medium">
        <div className="group-query-stock">
        <h3 style={{paddingBottom: '4px', textAlign: 'center'}} >Search a specific stock</h3>
          <form onSubmit={handleSubmit}>
            {/* <svg className="icon" aria-hidden="true" viewBox="0 0 24 24"><g><path d="M21.53 20.47l-3.66-3.66C19.195 15.24 20 13.214 20 11c0-4.97-4.03-9-9-9s-9 4.03-9 9 4.03 9 9 9c2.215 0 4.24-.804 5.808-2.13l3.66 3.66c.147.146.34.22.53.22s.385-.073.53-.22c.295-.293.295-.767.002-1.06zM3.5 11c0-4.135 3.365-7.5 7.5-7.5s7.5 3.365 7.5 7.5-3.365 7.5-7.5 7.5-7.5-3.365-7.5-7.5z"></path></g></svg> */}
            <input 
                    placeholder="Search a Stock by its ticker" 
                    type="search" 
                    className="input ibm-plex-sans-medium" 
                    onChange={handleChange} 
                    value={query}
                    ></input>
          </form>
        </div>
        <div className='stock-info-column'>
          {latestData ? (
            <p className="stock-year">Year: {latestYear.substring(0, 4)}</p>
            //fix this styling !!!! and show valid data 
          ):(
            <p>No data for this ticker</p>
          )}
        </div>
    </div>
  );
};

export default QueryStock;
