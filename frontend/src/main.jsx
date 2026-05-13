import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './styles/index.css'
import { ErrorBoundary } from './components/ErrorBoundary'
import { ThemeProvider } from './lib/ThemeProvider.jsx'

console.log("BUILD VERSION:", import.meta.env.VITE_APP_VERSION);

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary>
      <ThemeProvider>
        <App />
      </ThemeProvider>
    </ErrorBoundary>
  </React.StrictMode>,
)

// Force unregister any old service workers
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.getRegistrations().then(regs => {
    regs.forEach(reg => reg.unregister());
  });
}

// HMR debugging
if (import.meta.hot) {
  import.meta.hot.accept(() => {
    console.log("🔥 HMR update received");
  });
}
