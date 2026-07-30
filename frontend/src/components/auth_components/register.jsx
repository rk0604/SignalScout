import { useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { setSession, clearSession } from "../../api/client";

import "./auth_component_styles.css";

// Register Page Component
const RegisterPage = () => {
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
      const response = await api.post("/register", formdata);

      if (response.status === 200) {
        alert("Registration Successful");
        navigate("/"); // Redirect to the login page after successful registration
      }
    } catch (err) {
      if (err.response) {
        switch(err.response.status){
          case 400:
            alert('invalid credentials')
            console.log('invalid credentials')
            break;
          case 500:
            alert('sorry we could not register you at this moment')
            console.log('could not register user at this moment')
            break;
          default:
            console.warn('internal server error')
        }
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
    // Drop any previous session so a failed login can't leave a stale token behind.
    clearSession();
        try{
            const response = await api.post('/login', formdata);

            if(response.status === 200 && response.data?.token){
                // The token is now the credential; every later request carries it.
                setSession(response.data.token, response.data.email || formdata.email);
                navigate('/dashboard');
            }

        }catch(err){
            const {response} = err;
            if(response){
              switch(response.status){
                case 400:
                  console.log('invalid credentials')
                  alert('invalid credentials')
                  break;
                case 500:
                  console.warn('internal server error', err)
                  break;
                default:
                  console.log('internal server error: ', err)
              }
            } else{
              console.warn('error: ', err)
            }
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
