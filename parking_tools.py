from datetime import datetime, timedelta
from typing import Optional, List, Dict
from enum import Enum
from dataclasses import dataclass
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
import sqlite3

class ParkingType(Enum):
    STANDARD = "standard"
    DISABLED = "disabled"
    VIP = "vip"
    EMERGENCY = "emergency"

class ParkingStatus(Enum):
    AVAILABLE = "available"
    OCCUPIED = "occupied"
    RESERVED = "reserved"
    MAINTENANCE = "maintenance"

@dataclass
class ParkingSpot:
    spot_id: int
    level: str
    spot_number: str
    type: ParkingType
    status: ParkingStatus
    sensor_status: bool  # True if sensor is working

@tool
def get_parking_availability(
    arrival_time: Optional[datetime] = None,
    parking_type: Optional[ParkingType] = None,
    duration_hours: Optional[int] = None,
    *,
    config: RunnableConfig
) -> Dict:
    """Get real-time parking availability information"""
    conn = sqlite3.connect('hospital.sqlite')
    cursor = conn.cursor()

    try:
        query = """
            SELECT 
                p.area_id,
                p.level,
                p.total_spaces,
                p.parking_type,
                p.hourly_rate,
                COUNT(ps.spot_id) as total_spots,
                SUM(CASE WHEN ps.status = 'available' THEN 1 ELSE 0 END) as available_spots,
                COUNT(pr.reservation_id) as reserved_spots
            FROM parking_facilities p
            LEFT JOIN parking_spots ps ON p.area_id = ps.area_id
            LEFT JOIN parking_reservations pr ON p.area_id = pr.area_id
                AND pr.reservation_time BETWEEN ? AND datetime(?, '+' || ? || ' hours')
            WHERE 1=1
        """
        params = [
            arrival_time or datetime.now(),
            arrival_time or datetime.now(),
            duration_hours or 2
        ]

        if parking_type:
            query += " AND p.parking_type = ?"
            params.append(parking_type.value)

        query += " GROUP BY p.area_id, p.level"

        cursor.execute(query, params)
        results = cursor.fetchall()

        availability = {
            "timestamp": datetime.now().isoformat(),
            "areas": [],
            "total_available": 0,
            "total_capacity": 0
        }

        for result in results:
            (area_id, level, total_spaces, p_type, rate, 
             total_spots, available_spots, reserved_spots) = result
            
            current_available = available_spots - reserved_spots
            
            area_info = {
                "area_id": area_id,
                "level": level,
                "parking_type": p_type,
                "hourly_rate": rate,
                "total_spaces": total_spaces,
                "available_spaces": current_available,
                "reserved_spaces": reserved_spots,
                "occupancy_percentage": round((1 - current_available/total_spaces) * 100, 1)
            }
            
            availability["areas"].append(area_info)
            availability["total_available"] += current_available
            availability["total_capacity"] += total_spaces

        return availability

    finally:
        cursor.close()
        conn.close()

@tool
def reserve_parking_spot(
    area_id: int,
    arrival_time: datetime,
    duration_hours: int,
    parking_type: Optional[ParkingType] = ParkingType.STANDARD,
    *,
    config: RunnableConfig
) -> Dict:
    """Reserve a specific parking spot"""
    configuration = config.get("configurable", {})
    patient_id = configuration.get("patient_id")
    if not patient_id:
        raise ValueError("No patient ID configured.")

    conn = sqlite3.connect('hospital.sqlite')
    cursor = conn.cursor()

    try:
        cursor.execute('''
            SELECT ps.spot_id, ps.spot_number, p.hourly_rate
            FROM parking_spots ps
            JOIN parking_facilities p ON ps.area_id = p.area_id
            LEFT JOIN parking_reservations pr 
                ON ps.spot_id = pr.spot_id
                AND pr.reservation_time BETWEEN ? AND datetime(?, '+' || ? || ' hours')
            WHERE ps.area_id = ?
            AND ps.type = ?
            AND ps.status = 'available'
            AND pr.reservation_id IS NULL
            LIMIT 1
        ''', (arrival_time, arrival_time, duration_hours, area_id, parking_type.value))

        spot = cursor.fetchone()
        if not spot:
            return {"error": "No available parking spots for the selected criteria"}

        spot_id, spot_number, hourly_rate = spot
        total_cost = hourly_rate * duration_hours

        cursor.execute('''
            INSERT INTO parking_reservations (
                area_id, spot_id, patient_id, reservation_time,
                duration_hours, total_cost, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'confirmed', CURRENT_TIMESTAMP)
        ''', (area_id, spot_id, patient_id, arrival_time, 
              duration_hours, total_cost))

        reservation_id = cursor.lastrowid
        conn.commit()

        qr_code = f"PARKING-{reservation_id}-{spot_number}"

        return {
            "reservation_id": reservation_id,
            "spot_number": spot_number,
            "arrival_time": arrival_time.isoformat(),
            "duration_hours": duration_hours,
            "total_cost": total_cost,
            "qr_code": qr_code,
            "instructions": [
                f"Your reserved spot is {spot_number}",
                "Please arrive within 30 minutes of your reserved time",
                "Scan QR code at parking entrance",
                "Park only in your assigned spot",
                f"Maximum parking duration: {duration_hours} hours",
                "Contact parking office for extensions: 555-0123"
            ],
            "navigation_info": {
                "level": spot_number[:1],
                "zone": spot_number[1:2],
                "directions": [
                    "Enter through main parking entrance",
                    f"Follow signs to Level {spot_number[:1]}",
                    f"Your spot is in Zone {spot_number[1:2]}"
                ]
            }
        }

    except Exception as e:
        conn.rollback()
        return {"error": f"Failed to reserve parking: {str(e)}"}
    finally:
        cursor.close()
        conn.close()

@tool
def cancel_parking_reservation(
    reservation_id: int,
    *,
    config: RunnableConfig
) -> Dict:
    """Cancel a parking reservation"""
    configuration = config.get("configurable", {})
    patient_id = configuration.get("patient_id")
    if not patient_id:
        raise ValueError("No patient ID configured.")

    conn = sqlite3.connect('hospital.sqlite')
    cursor = conn.cursor()

    try:
        # Verify reservation exists and belongs to patient
        cursor.execute('''
            SELECT reservation_time, status, total_cost
            FROM parking_reservations
            WHERE reservation_id = ? AND patient_id = ?
        ''', (reservation_id, patient_id))
        
        reservation = cursor.fetchone()
        if not reservation:
            return {"error": "Reservation not found or unauthorized"}

        reservation_time = datetime.fromisoformat(reservation[0])
        if reservation_time < datetime.now() + timedelta(hours=2):
            return {"error": "Cancellations must be made at least 2 hours in advance"}

        if reservation[1] != 'confirmed':
            return {"error": f"Cannot cancel reservation with status: {reservation[1]}"}

        # Process cancellation
        cursor.execute('''
            UPDATE parking_reservations
            SET status = 'cancelled',
                cancelled_at = CURRENT_TIMESTAMP
            WHERE reservation_id = ?
        ''', (reservation_id,))

        conn.commit()

        return {
            "status": "cancelled",
            "refund_amount": reservation[2],
            "message": "Reservation cancelled successfully. Refund will be processed."
        }

    except Exception as e:
        conn.rollback()
        return {"error": f"Failed to cancel reservation: {str(e)}"}
    finally:
        cursor.close()
        conn.close()

