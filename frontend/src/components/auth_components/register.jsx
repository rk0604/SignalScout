import { useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";

import "./auth_component_styles.css";

// Register Page Component
const RegisterPage = () => {
  const API_URL = import.meta.env.VITE_API_URL; // Backend URL
  const navigate = useNavigate(); // Used to navigate to the login page after registration
  const [formdata, setFormdata] = useState({
    email: "",
    password: "",
    phone: "",
  });

  // Handles the form changes
  const handleChange = (e) => {
    setFormdata({
      ...formdata,
      [e.target.name]: e.target.value,
    });
  };

  // Handles the form submission
  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const response = await axios.post(`${API_URL}/register`, formdata, {
        withCredentials: true,
        headers: { "Content-Type": "application/json" },
      });

      if (response.status === 200) {
        alert("Registration Successful");
        navigate("/"); // Redirect to the login page after successful registration
      }
    } catch (err) {
      if (err.response) {
        console.error("Error:", err.response.data);
      } else {
        console.error("Unexpected error:", err);
      }
    }
  };

  return (
    <div className="page-container">
      <div className="form-container ibm-plex-sans-medium">
        <form className="form" onChange={handleChange} onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="email">Email</label>
            <input type="text" id="email" name="email" required />
          </div>

          <div className="form-group">
            <label htmlFor="phone">Phone #</label>
            <input type="tel" id="phone" name="phone" required />
          </div>

          <div className="form-group">
            <label htmlFor="password">Select a secure password</label>
            <input type="password" id="password" name="password" required />
          </div>
          <button className="form-submit-btn" type="submit">
            Submit
          </button>

          <button className="form-submit-btn" onClick={() => navigate("/")}>
            Login
          </button>
        </form>
      </div>
    </div>
  );
};

// Login Page Component
export function LoginPage() {
  const API_URL = import.meta.env.VITE_API_URL; // Backend URL
  const navigate = useNavigate(); // Used to navigate to the login page after registration
  const [formdata, setFormdata] = useState({
    email: "",
    password: "",
  });

  // Handles the form changes
  const handleChange = (e) => {
    setFormdata({
      ...formdata,
      [e.target.name]: e.target.value,
    });
  };

  const handleLogin = async(e) => {
    e.preventDefault();
        try{
            const response = await axios.post(`${API_URL}/login`, formdata, {
                withCredentials:true,
                headers: {  'Content-Type': 'application/json'}
            });

            if(response.status === 200){
                alert('Login Successful');
                navigate('/dashboard');
            }

        }catch(err){
            console.log(err);
        }
    }


  return (
    <div className="page-container">
      <div className="form-container ibm-plex-sans-medium">
        <form className="form" onSubmit={handleLogin} onChange={handleChange} >
          <div className="form-group">
            <label htmlFor="email">Email</label>
            <input type="text" id="email" name="email" required />
          </div>
          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input type="password" id="password" name="password" required />
          </div>
          <button className="form-submit-btn" type="submit">
            Submit
          </button>

          <button className="form-submit-btn" onClick={() => navigate("/register")}>
            Sign Up
          </button>
        </form>
      </div>
    </div>
  );
}

export default RegisterPage;
