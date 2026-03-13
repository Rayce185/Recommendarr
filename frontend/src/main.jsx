import React from 'react';
import ReactDOM from 'react-dom/client';
import Recommendarr from './App.jsx';
import ErrorBoundary from './components/ErrorBoundary.jsx';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary>
      <Recommendarr />
    </ErrorBoundary>
  </React.StrictMode>
);
