import { createContext, useEffect, useState } from 'react';
import PropTypes from 'prop-types'; // Import prop-types
import axios from 'axios';

// Create Context
export const StockContext = createContext();

// Provide Context to Components
export const StockProvider = ({ children }) => {
  const [pinnedStocks, setPinnedStocks] = useState([]);
  const [userEmail, setEmail] = useState('') //holds the user email necesary for querying pinned stocks
  const API_URL = import.meta.env.VITE_API_URL; // flask api url 

  // fetch the pinned stocks to be distributed amongst components
  const fetchPinnedStocks = async() =>{
    if(!userEmail){  return}
    try{
      const response = await axios.get(`${API_URL}/fetch-pins`, {
              params: { userEmail: userEmail }, 
              withCredentials: true, 
              headers: {
                  'Accept': 'application/json',
              }});
      
              if(response.status === 200){
                // console.log(response.data)
                setPinnedStocks(response.data)}
    }catch(err){
      console.log(err)
    }
  }

  useEffect(() => {
    setEmail(localStorage.getItem('email'));
  }, []);
  
  useEffect(() => {
    const timer = setTimeout(() => {
      fetchPinnedStocks()
      }, 500); // Delay execution to prevent rapid calls
    
      return () => clearTimeout(timer); 
  }, [userEmail]);
  

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
