import PropTypes from 'prop-types';
import './risk.css'
import api from '../../../api/client';
import { useState, useEffect } from 'react';

// used to present the risk analysis for a stock
const StockRisk = ({stock}) =>{
    const [volatility, setVolatility] = useState(null); // holds the annualized volatility of a stock
    const [debtToEquity, setDebtToEquity] = useState(null); // holds the debt to equity ratio
    const [currentRatio, setCurrentRatio] = useState(null); // holds the current rati
    const [quickRatio, setQuickRatio] = useState(null); // holds the quick ratio
    const [latestPrice, setLatestPrice] = useState(null); //holds the latest price

//-------------------------------------------------- routes ---------------------------------------------------------------------------------------

    //sends a request to the backend to fetch the risk analysis for a specific stock
    const fetchRiskAnal = async() =>{
        if(!stock){     return}
        const data_to_send = {stock: stock}

        try{
            const response = await api.post('/fetch-risk-anal', data_to_send);

            if(response && response.status === 200){
                // console.log(response.data)
                const {volatility, debtToEquity, currentRatio, quickRatio, latest_price} = response.data;
                setVolatility(volatility)
                setDebtToEquity(debtToEquity)
                setCurrentRatio(currentRatio)
                setQuickRatio(quickRatio)
                setLatestPrice(latest_price)
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
// -------------------------------------------------------- Helper functions -------------------------------------------------------------------------------
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
           {latestPrice? (
            <p className='ibm-plex-sans-heavy-ov'><span>Latest Price: </span>{latestPrice ? ("$"+latestPrice.toFixed(2)): "No data"}</p>
           ):(
            <p className='loading-text'>Unable to fetch latest price for: {stock}</p>
           )}
            
           {volatility? (
              <p className='ibm-plex-sans-heavy-ov'><span style={{ color: getColor(volatility) }} >Annual Volatility: </span>{volatility ? (volatility*100).toFixed(4): "No data"}%</p>
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
                <p className='loading-text'>Unable to fetch the current ratio for: {stock}</p>
            )}

            {quickRatio? (
                <p className='ibm-plex-sans-heavy-ov'><span>Quick Ratio: </span>{quickRatio ? (quickRatio.toFixed(4)): "No data"}</p>
            ):(
                <p className='loading-text'>Unable to fetch the quick ratio for: {stock}</p>
            )}

        </div>

        </>
    )
}

StockRisk.propTypes = {
    stock: PropTypes.string
}


export default StockRisk;
