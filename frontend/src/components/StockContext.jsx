import { createContext, useEffect, useState } from 'react';
import PropTypes from 'prop-types'; // Import prop-types
import api, { isLoggedIn } from '../api/client';

// Create Context
export const StockContext = createContext();

// Provide Context to Components
export const StockProvider = ({ children }) => {
  const [pinnedStocks, setPinnedStocks] = useState([]);

  // fetch the pinned stocks to be distributed amongst components.
  // The backend resolves the user from the bearer token, so no email is sent.
  const fetchPinnedStocks = async() =>{
    if(!isLoggedIn()){  return}
    try{
      const response = await api.get('/fetch-pins');

              if(response.status === 200){
                // console.log(response.data)
                setPinnedStocks(response.data)}
    }catch(err){
      console.log(err)
    }
  }

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchPinnedStocks()
      }, 500); // Delay execution to prevent rapid calls

      return () => clearTimeout(timer);
  }, []);


  return (
    <StockContext.Provider value={{ pinnedStocks, setPinnedStocks }}>
      {children}
    </StockContext.Provider>
  );
};

// Prop Validation
StockProvider.propTypes = {
  children: PropTypes.node.isRequired, // Ensures children is a valid React node
};

export default StockProvider;
