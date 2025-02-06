import axios from 'axios';
import "./holdings.css";
import { useState, useEffect } from 'react';

export function DisplayHoldings(){
    /**
     * 1. Helps a user keep track of all their holdings
     * 2. Fetches the user's holdings from the backend every 5 seconds, as a CRON job
     * 3. Displays the user's holdings in a table
     */
    const [holdings, setHoldings] = useState([]); // holds the user's holdings, and gets updated when user buys/sells a stock

// ------------------------------------------------ Functions -------------------------------------------------------------------------------------------------------
    
    const API_URL = import.meta.env.VITE_API_URL;

    // used to fetch the user's holdings from the backend
    const fetchHoldings = async () => {
        try{
            const response = await axios.post(`${API_URL}/get-holdings`,{
                withCredentials: true,
                headers: {
                    'Content-Type': 'application/json',
            }
        });
            if(response.status === 200){
                console.log(response.data)
                setHoldings(response.data);
            }
        } catch(err){
            const {response} = err;
            if(response){
                switch(response.status){
                    case 401:
                        console.log('unauthorized');
                        alert('unauthorized');
                        break;
                    case 500:
                        console.log('internal server error');
                        alert('internal server error');
                        break;
                    default:
                        console.log('unknown error');
                        alert('unknown error');
                        break;
                }
            } else{
                console.log(err);
                // alert('internal server error')
            }
        }
    }

// --------------------------------------------------- Use effect hooks ------------------------------------------------------------------------------------------------
    useEffect(() => {
        fetchHoldings();
    },[holdings]);

    return(
        <div className='holdings-container'>
            <div className="holdings-card">
                <h3>Your Holdings</h3>
                {holdings.length > 0 ?
                    holdings.map((holding, index) => {
                        return(
                            <div key={index} className="stock-holding-container">
                                <p>{holding.stock_name}</p>
                                <p>{holding.stock_symbol}</p>
                                <p>{holding.stock_quantity}</p>
                                <p>{holding.stock_price}</p>
                            </div>
                        )
                    })
                    :
                    <h4>Buy something first, broke ass</h4>
                }
                
            </div>
        </div>
    )
}

export default DisplayHoldings;




