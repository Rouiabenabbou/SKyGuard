import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import LoginPage from "./components/LoginPage.jsx";
import { AuthProvider, useAuth } from "./auth.jsx";
import "leaflet/dist/leaflet.css";
import "./styles/global.css";
import "./styles/soc.css";

// v1.1: the dashboard opens only after a successful login.
function Gate() {
  const { loading, user } = useAuth();
  if (loading) return <div className="login-page"><div className="muted">Loading…</div></div>;
  if (!user) return <LoginPage />;
  return <App key={user.username} />;
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <AuthProvider>
      <Gate />
    </AuthProvider>
  </React.StrictMode>
);
