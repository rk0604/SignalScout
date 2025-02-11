import PropTypes from 'prop-types';
import './risk.css'
import axios from 'axios';
import { useState, useEffect } from 'react';

// used to present the risk analysis for a stock 
const StockRisk = ({stock}) =>{
    const API_URL = import.meta.env.VITE_API_URL;
    const [riskAnalysis, setRiskAnalysis] = useState(''); //holds the backend processed risk analysis for a stock

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

    return(
        <>
        <h2>Stowing the risk analysis for {stock}</h2>
        </>
    )
}

StockRisk.protoTypes = {
    stock: PropTypes.string.isRequired
}


export default StockRisk;
