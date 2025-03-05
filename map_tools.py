from typing import Optional, List, Dict
from datetime import datetime, timedelta
import googlemaps
from dataclasses import dataclass
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
import os
from dotenv import load_dotenv

# Set up Google Maps API client
load_dotenv()
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)

# Hospital main address constants
HOSPITAL_ADDRESS = "251 E Huron St, Chicago, IL 60611"
HOSPITAL_LOCATION = {
    "lat": 41.8947,
    "lng": -87.6214
}

@dataclass
class TransportRoute:
    """Route information data class"""
    type: str  # transportation mode
    duration: int  # estimated duration (minutes)
    duration_in_traffic: Optional[int]  # duration considering traffic (minutes)
    distance: float  # distance (kilometers)
    steps: List[str]  # navigation steps
    arrival_time: Optional[str]  # estimated arrival time
    departure_time: Optional[str]  # suggested departure time

@tool
def get_route_to_hospital(
    start_address: str,
    mode: str = "driving",
    arrival_time: Optional[datetime] = None,
    *,
    config: RunnableConfig
) -> Dict:
    """
    Get navigation information to the hospital
    
    Args:
        start_address: Starting address
        mode: Transportation mode (driving/walking/transit/bicycling)
        arrival_time: Desired arrival time
        
    Returns:
        Dictionary containing route information
    """
    try:  
        # Get route planning
        now = datetime.now()
        directions = gmaps.directions(
            start_address,
            HOSPITAL_ADDRESS,
            mode=mode,
            arrival_time=arrival_time or now,
            alternatives=True,
            traffic_model='best_guess' if mode == 'driving' else None
        )

        if not directions:
            return {"error": "No routes found"}

        print(directions)

        routes = []
        for route in directions:
            leg = route['legs'][0]
            
            # Extract navigation steps
            steps = []
            for step in leg['steps']:
                instruction = step['html_instructions']
                # Clean HTML tags
                instruction = instruction.replace('<b>', '').replace('</b>', '')
                instruction = instruction.replace('<div style="font-size:0.9em">', ' - ')
                instruction = instruction.replace('</div>', '')
                steps.append(instruction)
            print(steps)
            # Calculate arrival and departure times
            duration_seconds = leg['duration']['value']
            if arrival_time:
                suggested_departure = arrival_time - timedelta(seconds=duration_seconds)
                arrival_str = arrival_time.strftime("%Y-%m-%d %H:%M")
                departure_str = suggested_departure.strftime("%Y-%m-%d %H:%M")
            else:
                arrival_str = (now + timedelta(seconds=duration_seconds)).strftime("%Y-%m-%d %H:%M")
                departure_str = now.strftime("%Y-%m-%d %H:%M")

            route_info = TransportRoute(
                type=mode,
                duration=duration_seconds // 60,  # convert to minutes
                duration_in_traffic=leg.get('duration_in_traffic', {}).get('value', None),
                distance=leg['distance']['value'] / 1000,  # convert to kilometers
                steps=steps,
                arrival_time=arrival_str,
                departure_time=departure_str
            )
            routes.append(route_info)

        return {
            "start_address": start_address,
            "destination": HOSPITAL_ADDRESS,
            "routes": [vars(route) for route in routes],
            "traffic_conditions": get_traffic_conditions() if mode == 'driving' else None
        }

    except Exception as e:
        return {"error": f"Failed to get route: {str(e)}"}

@tool
def get_estimated_arrival_time(
    start_address: str,
    departure_time: Optional[datetime] = None,
    mode: str = "driving",
    *,
    config: RunnableConfig
) -> Dict:
    """
    Calculate estimated arrival time to the hospital
    
    Args:
        start_address: Starting address
        departure_time: Departure time (defaults to current time)
        mode: Transportation mode
        
    Returns:
        Estimated arrival time information
    """
    try:
        departure_time = departure_time or datetime.now()
        
        # Get route planning
        directions = gmaps.directions(
            start_address,
            HOSPITAL_ADDRESS,
            mode=mode,
            departure_time=departure_time,
            traffic_model='best_guess' if mode == 'driving' else None
        )

        if not directions:
            return {"error": "Unable to calculate arrival time"}

        leg = directions[0]['legs'][0]
        duration_seconds = leg.get('duration_in_traffic', leg['duration'])['value']
        
        estimated_arrival = departure_time + timedelta(seconds=duration_seconds)
        
        return {
            "departure_time": departure_time.strftime("%Y-%m-%d %H:%M"),
            "estimated_arrival": estimated_arrival.strftime("%Y-%m-%d %H:%M"),
            "duration_minutes": duration_seconds // 60,
            "distance_km": leg['distance']['value'] / 1000,
            "traffic_condition": "Normal" if duration_seconds <= leg['duration']['value'] else "Heavy"
        }

    except Exception as e:
        return {"error": f"Failed to calculate arrival time: {str(e)}"}

def get_traffic_conditions() -> Dict:
    """Get real-time traffic conditions around the hospital"""
    try:
        # Get nearby roads information
        print("get_traffic_conditions")
        roads = gmaps.places_nearby(
            location=(HOSPITAL_LOCATION['lat'], HOSPITAL_LOCATION['lng']),
            radius=1000,
            type='route'
        )
        print(roads)
        traffic_conditions = {
            "hospital_name": "Northwestern Memorial Hospital",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "overall_status": "Normal",
            "nearby_roads": []
        }

        for road in roads.get('results', [])[:5]:
            road_details = gmaps.place(road['place_id'])['result']
            traffic_conditions["nearby_roads"].append({
                "name": road_details.get('name', 'Unknown Road'),
                "status": "Normal",  # Can be updated with real traffic data
                "congestion_level": "Light"  # Can be updated with real traffic data
            })

        return traffic_conditions

    except Exception as e:
        return {"error": f"Failed to get traffic conditions: {str(e)}"}