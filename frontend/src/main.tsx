import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";

class PageGuard extends React.Component<{ children: React.ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 24, background: "#111", color: "#f5f5f5" }}>
        <div>
          <p style={{ fontWeight: 700 }}>صفحه خطا داد و سیاه نماند.</p>
          <button type="button" style={{ marginTop: 12 }} onClick={() => window.location.reload()}>بارگذاری دوباره</button>
        </div>
      </div>
    );
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <PageGuard>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </PageGuard>
  </React.StrictMode>
);
