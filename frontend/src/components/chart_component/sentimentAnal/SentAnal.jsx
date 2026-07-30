import './sentiment.css';
import { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import api from '../../../api/client';


// Maps a polarity score to the shared gain/loss colour semantics.
const sentimentColor = (polarity) => {
    if (polarity >= 0.15) return '#16C784';   // positive
    if (polarity <= -0.15) return '#EA3943';  // negative
    return '#A7B0BC';                         // neutral
};

const formatPolarity = (polarity) =>
    `${polarity > 0 ? '+' : ''}${polarity.toFixed(2)}`;

function SentimentAnalysis({stock}){
    const [newsData, setNewsData] = useState([]) //hold the news data for the stock
    // each element has headline, link and a sentiment object
    const [overall, setOverall] = useState(null); // aggregate sentiment across headlines
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState(null);

    // Clear stale results when the ticker changes, so a previous stock's
    // headlines aren't shown under a new ticker.
    useEffect(() => {
        setNewsData([]);
        setOverall(null);
        setError(null);
    }, [stock]);

    const fetchSentiAnal = async() =>{
        if(!stock){
            console.log('select a stock first')
            return
        }
        setIsLoading(true);
        setError(null);
        try{
            console.log('fetching sentiment analysis for: ', stock)
            const response = await api.get('/get-sentiment-analysis',{
                params: {stock},
              });

              if(response.status === 200){
                setNewsData(response.data.news || [])
                setOverall(response.data.overall_sentiment || null)
              }

        }catch(err){
            const {response} = err;
            switch(response?.status){
                case 400:
                    setError('Invalid ticker');
                    break;
                case 404:
                    setError(`No news found for ${stock}`);
                    break;
                case 503:
                    setError('News source unavailable right now');
                    break;
                default:
                    setError('Could not load news');
                    break;
            }
        }finally{
            setIsLoading(false);
        }
    }

    return(
        <div className='sentiment-info-container'>
        <div className='sentiment-info'>
            <h1>Latest News: </h1>
            <button onClick={()=>{fetchSentiAnal()}} disabled={isLoading} >
                {isLoading ? 'Loading…' : 'Get Latest News'}
            </button>

            {/* Aggregate sentiment across the scored headlines */}
            {overall && (
                <div className='sentiment-summary ibm-plex-sans-medium'>
                    <span
                        className='sentiment-badge'
                        style={{ color: sentimentColor(overall.polarity), borderColor: sentimentColor(overall.polarity) }}
                    >
                        {overall.label} {formatPolarity(overall.polarity)}
                    </span>
                    <span className='sentiment-breakdown'>
                        {overall.positive} pos · {overall.neutral} neu · {overall.negative} neg
                        {' '}of {overall.headline_count}
                    </span>
                </div>
            )}

            <div className='news-display'>
                {error ? (
                    <h3 className='loading-text'>{error}</h3>
                ) : newsData.length > 0 ? (
                    newsData.map((newsItem, index) => (
                        <div key={index} className='ticker-sentiment-data-display ibm-plex-sans-medium'>
                            <div className='headline-row'>
                                {newsItem.sentiment && (
                                    <span
                                        className='headline-score'
                                        style={{ color: sentimentColor(newsItem.sentiment.polarity) }}
                                        title={`TextBlob ${newsItem.sentiment.textblob_polarity} + finance lexicon ${newsItem.sentiment.lexicon_adjustment}`}
                                    >
                                        {formatPolarity(newsItem.sentiment.polarity)}
                                    </span>
                                )}
                                <h3>{newsItem.headline}</h3>
                            </div>
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

SentimentAnalysis.propTypes = {
    stock: PropTypes.string,
}

export default SentimentAnalysis


