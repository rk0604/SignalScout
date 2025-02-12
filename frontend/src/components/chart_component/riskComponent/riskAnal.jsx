import PropTypes from 'prop-types';
import './risk.css'
import axios from 'axios';
import { useState, useEffect } from 'react';

// used to present the risk analysis for a stock 
const StockRisk = ({stock}) =>{
    const API_URL = import.meta.env.VITE_API_URL;
    const [riskAnalysis, setRiskAnalysis] = useState(''); //holds the backend processed risk analysis for a stock
    const [volatility, setVolatility] = useState(null); // holds the annualized volatility of a stock

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
                console.log(`${response.data}`);
                setVolatility(response.data.volatility)
                setRiskAnalysis(response.data);
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
              <p className='ibm-plex-sans-heavy-ov'
                style={{color: getColor(volatility)}}
               ><span style={{ color: getColor(volatility) }} >Annual Volatility: </span>{volatility ? (volatility.toFixed(4)*100): "No data"}%</p>
           ):(
              <p className='loading-text'>Fetching the risk analysis for: {stock}</p>
            )}

        </div>

        </>
    )
}

StockRisk.protoTypes = {
    stock: PropTypes.string.isRequired
}


export default StockRisk;
