import { useState } from "react";
import './stockRec.css';
import PropTypes from "prop-types";

//this component is used to display the recommendations and handles the processing 
export function Recommendations() {
  const API_URL = import.meta.env.VITE_API_URL; // Backend API URL
  const [recommendations, setRecommendations] = useState([
    { stock: "AAPL", rating: "Strong Buy" },
    { stock: "TSLA", rating: "Strong Sell" },
    { stock: "AMD", rating: "Sell" },
    { stock: "NVDA", rating: "Buy" },
    { stock: "GOOGL", rating: "Strong Buy" },
    { stock: "MSFT", rating: "Hold" },
    { stock: "NFLX", rating: "Sell" },
    { stock: "AMZN", rating: "Buy" },
    { stock: "META", rating: "Strong Buy" },
    { stock: "BABA", rating: "Hold" },
    { stock: "DIS", rating: "Sell" },
    { stock: "PYPL", rating: "Buy" },
    { stock: "KO", rating: "Hold" },
    { stock: "PEP", rating: "Strong Buy" },
    { stock: "XOM", rating: "Strong Sell" },
  ]);
  

  return (
    <div className="recommend-card">
      <h3 className="recommend-title">Recommendations</h3>
      <div className="recommend-grid">
        {recommendations.map((rec, index) => (
          <RecContainer key={index} stock={rec.stock} rating={rec.rating} />
        ))}
      </div>
    </div>
  );
}



// ----------------------------------------------------------- stock rec component -----------------------------------------------------------

const RecContainer = ({ stock, rating }) => {
    const getColor = () => {
      switch (rating) {
        case "Strong Buy": return "#7CFC00";  // Green
        case "Buy": return "#0BDA51";        // Blue
        case "Hold": return "#2196F3";       // Yellow
        case "Sell": return "#FA5F55";       // Orange
        case "Strong Sell": return "#D2042D"; // Red
        default: return "#FFFFFF";           // Default White
      }
    };
  
    //UPON CLICK SHOULD OPEN A MODAL WITH ANALYSIS AND STOCK INFO 
    return (
      <div 
        className="rec-container" 
        style={{ borderColor: getColor(), color: getColor(), backgroundColor: rating === "Strong Buy" ? "#F0FFF0" : "#FFFFFF" }}
      >
        <h2>{stock}</h2>
        <p>{rating}</p>
      </div>
    );
  };  
  
    RecContainer.prototype = {
        stock: PropTypes.string.isRequired,
        rating: PropTypes.string.isRequired
    }

  