from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
from geopy.distance import geodesic
from datetime import datetime
import os

app = FastAPI(title="Accident Alert API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY", "")

async def fetch_tomtom_incidents(lat, lon, radius_miles=20):
    lat_delta = radius_miles / 69.0
    lon_delta = radius_miles / 54.0
    
    min_lat = lat - lat_delta
    max_lat = lat + lat_delta
    min_lon = lon - lon_delta
    max_lon = lon + lon_delta
    
    url = "https://api.tomtom.com/traffic/services/5/incidentDetails"
    
    params = {
        "key": TOMTOM_API_KEY,
        "bbox": f"{min_lon},{min_lat},{max_lon},{max_lat}",
        "language": "en-US",
        "categoryFilter": "0,1,2"
    }
    
    incidents = []
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            for item in data.get("incidents", []):
                props = item.get("properties", {})
                geom = item.get("geometry", {})
                coords_raw = geom.get("coordinates", [])
                
                if not coords_raw or len(coords_raw) == 0:
                    continue
                
                first_coord = coords_raw[0]
                if not isinstance(first_coord, list) or len(first_coord) < 2:
                    continue
                    
                inc_lon = first_coord[0]
                inc_lat = first_coord[1]
                
                icon_category = props.get("iconCategory", 999)
                events = props.get("events", [])
                
                if events and len(events) > 0:
                    incident_type = events[0].get("description", "Traffic Incident")
                else:
                    category_names = {
                        0: "Accident", 1: "Accident", 2: "Accident",
                        3: "Dangerous Conditions", 4: "Rain", 5: "Ice",
                        6: "Road Closed", 7: "Road Works", 8: "Wind",
                        9: "Flooding", 10: "Detour", 11: "Cluster"
                    }
                    incident_type = category_names.get(icon_category, "Traffic Incident")
                
                from_str = props.get("from", "")
                to_str = props.get("to", "")
                if from_str and to_str:
                    address = f"{from_str} to {to_str}"
                elif from_str:
                    address = from_str
                elif to_str:
                    address = f"Near {to_str}"
                else:
                    address = "Unknown location"
                
                incident = {
                    "id": item.get("id", str(len(incidents))),
                    "type": incident_type,
                    "address": address.strip(),
                    "location": {"latitude": inc_lat, "longitude": inc_lon},
                    "timestamp": datetime.now().isoformat(),
                    "distance_miles": 0.0,
                    "severity": str(props.get("magnitudeOfDelay", 0)),
                    "delay": int(props.get("delay", 0))
                }
                incidents.append(incident)
    
    except Exception as e:
        print(f"Error: {e}")
    
    return incidents

@app.get("/")
async def root():
    return {"status": "online", "service": "Accident Alert API"}

@app.get("/incidents/nearby")
async def get_nearby_incidents(max_distance: int = 20):
    user_lat = 33.4484
    user_lon = -112.0740
    
    incidents = await fetch_tomtom_incidents(user_lat, user_lon, max_distance)
    
    filtered = []
    for inc in incidents:
        inc_lat = inc["location"]["latitude"]
        inc_lon = inc["location"]["longitude"]
        distance = geodesic((user_lat, user_lon), (inc_lat, inc_lon)).miles
        
        if distance <= max_distance:
            inc["distance_miles"] = round(distance, 1)
            filtered.append(inc)
    
    filtered.sort(key=lambda x: x["distance_miles"])
    
    return {
        "user_location": {"latitude": user_lat, "longitude": user_lon},
        "incidents": filtered,
        "count": len(filtered)
    }
