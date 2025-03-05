import './sentiment.css';
import { useState } from 'react';
import axios from 'axios';


function SentimentAnalysis({stock}){
    const API_URL = import.meta.env.VITE_API_URL; // backend api url
    const [selectedStock, setSelectedStock] = useState(stock || null); //
    const [newsData, setNewsData] = useState([]) //hold the news data for the stock
    // every element inside the newsData[] has two attributes, headline and link

    const fetchSentiAnal = async() =>{
        if(!selectedStock){
            console.log('select a stock first')
            return
        }
        try{
            console.log('fetching sentiment analysis for: ', selectedStock)
            const response = await axios.get(`${API_URL}/get-sentiment-analysis`,{
                params: {stock: selectedStock},
                withCredentials: true, 
                headers: {
                    'Accept': 'application/json',
                }
              });

              if(response.status === 200){
                console.log('response: ', response.data.ticker);
                console.log('news: ', response.data.news[0]); //.headline and .link attributes
                setNewsData(response.data.news)
              }

        }catch(err){
            const {response} = err;
            switch(response.status){
                case 400:
                    console.log('invalid query/credentials')
                    break;
                default:
                    console.warn('internal server error');
                    break;
            }
        }
    }

    return(
        <div className='sentiment-info-container'>
        <div className='sentiment-info'>
            <h1>Latest News: </h1>
            <button onClick={()=>{fetchSentiAnal()}} >Get Latest News</button>
            <div className='news-display'>
                {newsData.length > 0 ? (
                    newsData.map((newsItem, index) => (
                        <div key={index} className='ticker-sentiment-data-display ibm-plex-sans-medium'>
                            <h3>{newsItem.headline}</h3>
                            <a href={newsItem.link} target="_blank" rel="noopener noreferrer">{newsItem.link}</a>
                        </div>
                    ))
                ) : (
                    <h3 className='loading-text'>No sentiment analysis for this ticker :(</h3>
                )}
            </div>
        </div>
        </div>
    )
}

export default SentimentAnalysis


