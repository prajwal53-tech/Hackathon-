import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import L from 'leaflet'

// Fix default Leaflet icon URLs when bundling
// @ts-ignore
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
// @ts-ignore
import markerIcon from 'leaflet/dist/images/marker-icon.png'
// @ts-ignore
import markerShadow from 'leaflet/dist/images/marker-shadow.png'

// @ts-ignore
delete (L.Icon.Default.prototype as any)._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
