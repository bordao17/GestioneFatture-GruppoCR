import React from 'react'
import ReactDOM from 'react-dom/client'
import 'bootstrap/dist/css/bootstrap.min.css'
// Dopo Bootstrap: gli stili del guscio (barra laterale, barra in alto) devono
// poter vincere sulle utility, e usano le sue variabili per seguire il tema.
import './index.css'
import App from './App.jsx'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
