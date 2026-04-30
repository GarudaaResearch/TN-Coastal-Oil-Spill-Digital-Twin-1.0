# TN Coastal Oil Spill Digital Twin 1.0

**AI-Driven Bio-Adaptive Routing · Buoyant WSN · Magnetic Hydrochar · Tamil Nadu 2026**

> Developed by **Prof. Anjit Raja R** — ANJIT SCHOOL OF AI & ISC-RCAS

---

## 🌊 Overview

A real-time digital twin platform simulating coastal oil spill dynamics along the Tamil Nadu coastline. Integrates:

- **FastAPI** backend with WebSocket-based real-time simulation (2 Hz)
- **React + Vite** frontend with interactive **Leaflet satellite map**
- **WSN routing** (ACO / GEA-R / Q-Learn algorithms)
- **Magnetic Hydrochar** adsorption modelling
- **Oil advection-diffusion-decay** physics engine

---

## 🗺️ Regions Simulated

| Zone | Sensitivity | Feature |
|------|-------------|---------|
| Coromandel Coast | 55% | High-energy open coast |
| Palk Bay | 70% | Semi-enclosed tidal bay |
| Gulf of Mannar | 95% | Coral reef biodiversity |
| Mangroves/Estuaries | 100% | Critical ecological zone |

---

## 🚀 Local Development

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Frontend: http://localhost:5173  
Backend API: http://localhost:8000

---

## 🌐 Deployment

### Frontend (Netlify)
The `netlify.toml` at the root handles the build automatically.

Set these **Environment Variables** in Netlify dashboard:
```
VITE_WS_URL  = wss://your-backend-url/ws/simulation
VITE_API_URL = https://your-backend-url
```

### Backend
Deploy the `backend/` folder to any Python host:
- [Render](https://render.com) — free tier available
- [Railway](https://railway.app)
- [Heroku](https://heroku.com)

---

## 🎨 Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, Vite, Leaflet.js |
| Styling | Vanilla CSS (Dark Slate + Teal + Violet) |
| Charts | Chart.js / react-chartjs-2 |
| Backend | FastAPI, Uvicorn, WebSockets |
| Simulation | NumPy, SciPy |
| Map tiles | ESRI Satellite (free) + CartoDB labels |

---

## 📄 License

© 2026 Prof. Anjit Raja R — ANJIT SCHOOL OF AI & ISC-RCAS. All rights reserved.
