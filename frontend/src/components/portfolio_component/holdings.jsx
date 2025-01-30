import axios from 'axios';
import "./holdings.css";
// import { useState } from 'react';

export function DisplayHoldings(){
    const API_URL = import.meta.env.VITE_API_URL; // flask backend url 

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
            }
        } catch(err){
            console.log(err)
        }
    
    }

    return(
        <div className='holdings-container'>
            <button className='holdings-button' onClick={fetchHoldings}>Holdings</button>
            <div className="holdings-card">
                <h3>Your Holdings</h3>
                {/* <DisplayHoldings /> */}
            </div>
        </div>
    )
}

export default DisplayHoldings;




