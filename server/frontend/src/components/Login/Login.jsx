import React, { useState } from 'react';
import "./Login.css";
import Header from '../Header/Header';

const Login = ({ onClose }) => {
  const [userName, setUserName] = useState("");
  const [password, setPassword] = useState("");

  // Fix: Added the trailing slash for Django compatibility
  let login_url = window.location.origin + "/djangoapp/login/";

  const login = async (e) => {
    e.preventDefault();

    const res = await fetch(login_url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        "userName": userName,
        "password": password
      }),
    });

    const json = await res.json();
    if (json.status != null && json.status === "Authenticated") {
      sessionStorage.setItem('username', json.userName);
      window.location.href = "/"; // Success redirect
    }
    else {
      alert("The user could not be authenticated.");
    }
  };

  return (
    <div>
      <Header />
      <div onClick={onClose}>
        <div
          onClick={(e) => { e.stopPropagation(); }}
          className='modalContainer'
        >
          <form className="login_panel" onSubmit={login}>
            {/* Added margin-bottom style for spacing between fields */}
            <div style={{ marginBottom: "15px" }}>
              <span className="input_field">Username </span>
              <input 
                type="text" 
                name="username" 
                placeholder="Username" 
                className="input_field" 
                onChange={(e) => setUserName(e.target.value)} 
              />
            </div>

            <div style={{ marginBottom: "15px" }}>
              <span className="input_field">Password </span>
              <input 
                name="psw" 
                type="password" 
                placeholder="Password" 
                className="input_field" 
                onChange={(e) => setPassword(e.target.value)} 
              />
            </div>

            {/* Buttons container: display flex ensures they stay side-by-side */}
            <div style={{ display: "flex", gap: "10px", marginTop: "20px" }}>
              <input className="action_button" type="submit" value="Login" />
              <input 
                className="action_button" 
                type="button" 
                value="Cancel" 
                onClick={() => window.location.href = "/"} 
              />
            </div>
            
            <div style={{ marginTop: "15px" }}>
              <a className="loginlink" href="/register">Register Now</a>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};

export default Login;