import PropTypes from 'prop-types';
import './risk.css'
import axios from 'axios';
import { useState, useEffect } from 'react';

// used to present the risk analysis for a stock 
const StockRisk = ({stock}) =>{
    const API_URL = import.meta.env.VITE_API_URL;
    const [volatility, setVolatility] = useState(null); // holds the annualized volatility of a stock
    const [debtToEquity, setDebtToEquity] = useState(null); // holds the debt to equity ratio
    const [currentRatio, setCurrentRatio] = useState(null); // holds the current rati
    const [quickRatio, setQuickRatio] = useState(null); // holds the quick ratio

//-------------------------------------------------- routes ---------------------------------------------------------------------------------------

    //sends a request to the backend to fetch the risk analysis for a specific stock
    const fetchRiskAnal = async() =>{
        if(!stock){     return}
        const data_to_send = {stock: stock}

        try{
            const response = await axios.post(`${API_URL}/fetch-risk-anal`, data_to_send, {
                withCredentials:true,
                headers: {
                    "Content-Type": "application/json"
                }
            });

            if(response && response.status === 200){
                console.log(response.data);
                const {volatility, debtToEquity, currentRatio, quickRatio} = response.data;
                setVolatility(volatility)
                setDebtToEquity(debtToEquity)
                setCurrentRatio(currentRatio)
                setQuickRatio(quickRatio)
            }

        }catch(err){
            const {response} = err;
            if(response){
                switch(response.status){
                    case 400:
                        console.log('invalid ticker');
                        break;
                    default:
                        console.warn('internal server error');
                }
            }
            else{
                console.log('an error occurred: ', err)
            }
        }
    }

// ----------------------------------------------------- useEffect() hooks -------------------------------------------------------------------------------------------------

//main useEffect hook
    useEffect(()=>{
        const timer = setTimeout(()=>{
            fetchRiskAnal();
        }, 500)

        return () => clearTimeout(timer); // reset the timer
    },[stock])

    const getColor = (volatility) => {
        if (volatility < 0.15) return "#7CFC00";
        if (volatility >= 0.15 && volatility < 0.30) return "#0BDA51";
        if (volatility > 0.30 && volatility < 0.5) return "#FA5F55";
        if (volatility >= 0.5) return "#D2042D";
        return "#000"; // Default case (optional)
    };    

    return(
        <>
        <div className='risk-info'>
           {volatility? (
              <p className='ibm-plex-sans-heavy-ov'><span style={{ color: getColor(volatility) }} >Annual Volatility: </span>{volatility ? (volatility.toFixed(4)*100): "No data"}%</p>
           ):(
              <p className='loading-text'>Fetching the volatility analysis for: {stock}</p>
            )}

            {/* Debt to Equity ratio */}
            {debtToEquity? (
                <p className='ibm-plex-sans-heavy-ov' style={{color: '#FFFFFF'}} ><span>Debt to Equity Ratio: </span>{debtToEquity ? (debtToEquity.toFixed(4)): "No data"}</p>
            ):(
                <p className='loading-text'>Fetching the debt to equity ratio for: {stock}</p>
            )}

            {/* Current ratio */}
            {currentRatio? (
                <p className='ibm-plex-sans-heavy-ov'><span>Current Ratio: </span>{currentRatio ? (currentRatio.toFixed(4)): "No data"}</p>
            ):(
                <p className='loading-text'>Fetching the current ratio for: {stock}</p>
            )}

            {quickRatio? (
                <p className='ibm-plex-sans-heavy-ov'><span>Quick Ratio: </span>{quickRatio ? (quickRatio.toFixed(4)): "No data"}</p>
            ):(
                <p className='loading-text'>Fetching the quick ratio for: {stock}</p>
            )}

        </div>

        </>
    )
}

StockRisk.protoTypes = {
    stock: PropTypes.string.isRequired
}


export default StockRisk;
