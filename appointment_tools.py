from typing import Optional, List, Union
from datetime import datetime, timedelta
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
import sqlite3
from enum import Enum
from dataclasses import dataclass
# 定义一些常量和枚举
class AppointmentStatus(Enum):
    SCHEDULED = 'scheduled'
    COMPLETED = 'completed'
    CANCELLED = 'cancelled'
    NO_SHOW = 'no_show'

class DoctorTitle(Enum):
    CHIEF = 'Chief Physician'
    ASSOCIATE_CHIEF = 'Associate Chief Physician'
    ATTENDING = 'Attending Physician'
    RESIDENT = 'Resident Physician'

@dataclass
class TimeSlot:
    start_time: datetime
    end_time: datetime
    is_available: bool

class WorkingHours:
    MORNING_START = '09:00'
    MORNING_END = '12:00'
    AFTERNOON_START = '14:00'
    AFTERNOON_END = '17:00'
    APPOINTMENT_DURATION = 30  # minutes

def validate_appointment_time(doctor_id: int, scheduled_time: datetime) -> tuple[bool, str]:
    """Validate if the appointment time is valid"""
    conn = sqlite3.connect('hospital.sqlite')
    cursor = conn.cursor()

    try:
        # Get doctor's working days and hours
        cursor.execute('''
            SELECT working_days, working_hours, max_daily_appointments 
            FROM doctors WHERE doctor_id = ?
        ''', (doctor_id,))
        doctor_schedule = cursor.fetchone()
        
        if not doctor_schedule:
            return False, "Doctor not found"

        working_days, working_hours, max_daily_appointments = doctor_schedule
        
        # Check if it's a working day
        if working_days and scheduled_time.strftime('%A') not in working_days.split(','):
            return False, "Doctor is not available on this day"

        # Check working hours
        if working_hours:
            start_time, end_time = working_hours.split('-')
            work_start = datetime.strptime(start_time, '%H:%M').time()
            work_end = datetime.strptime(end_time, '%H:%M').time()
            
            if not (work_start <= scheduled_time.time() <= work_end):
                return False, "Appointment time is outside working hours"

        # Check number of appointments for the day
        cursor.execute('''
            SELECT COUNT(*) FROM appointments 
            WHERE doctor_id = ? 
            AND date(scheduled_time) = date(?) 
            AND status = 'scheduled'
        ''', (doctor_id, scheduled_time))
        
        daily_appointments = cursor.fetchone()[0]
        if daily_appointments >= max_daily_appointments:
            return False, "Doctor's schedule is full for this day"

        # Check if the time slot is available
        appointment_end = scheduled_time + timedelta(minutes=WorkingHours.APPOINTMENT_DURATION)
        cursor.execute('''
            SELECT COUNT(*) FROM appointments 
            WHERE doctor_id = ? 
            AND scheduled_time < ? 
            AND end_time > ?
            AND status = 'scheduled'
        ''', (doctor_id, appointment_end, scheduled_time))
        
        if cursor.fetchone()[0] > 0:
            return False, "Time slot is already booked"

        return True, "Time slot is available"

    finally:
        cursor.close()
        conn.close()

def get_available_slots(doctor_id: int, date: datetime) -> List[TimeSlot]:
    """Get available appointment slots for a specific doctor and date"""
    conn = sqlite3.connect('hospital.sqlite')
    cursor = conn.cursor()

    try:
        # Get doctor's schedule
        cursor.execute('''
            SELECT working_days, working_hours 
            FROM doctors 
            WHERE doctor_id = ?
        ''', (doctor_id,))
        schedule = cursor.fetchone()
        
        if not schedule:
            return []

        working_days, working_hours = schedule
        
        # Check if the doctor works on this day
        if working_days and date.strftime('%A') not in working_days.split(','):
            return []

        # Get working hours
        start_time, end_time = working_hours.split('-')
        day_start = datetime.combine(date.date(), 
                                   datetime.strptime(start_time, '%H:%M').time())
        day_end = datetime.combine(date.date(), 
                                  datetime.strptime(end_time, '%H:%M').time())

        # Get all appointments for the day
        cursor.execute('''
            SELECT scheduled_time, end_time 
            FROM appointments 
            WHERE doctor_id = ? 
            AND date(scheduled_time) = date(?)
            AND status = 'scheduled'
            ORDER BY scheduled_time
        ''', (doctor_id, date))
        
        booked_slots = cursor.fetchall()

        # Generate available time slots
        available_slots = []
        current_time = day_start

        while current_time + timedelta(minutes=WorkingHours.APPOINTMENT_DURATION) <= day_end:
            slot_end = current_time + timedelta(minutes=WorkingHours.APPOINTMENT_DURATION)
            
            # Check if slot overlaps with any booked appointments
            is_available = True
            for booked_start, booked_end in booked_slots:
                booked_start = datetime.strptime(booked_start, '%Y-%m-%d %H:%M:%S')
                booked_end = datetime.strptime(booked_end, '%Y-%m-%d %H:%M:%S')
                
                if (current_time < booked_end and slot_end > booked_start):
                    is_available = False
                    break

            if is_available:
                available_slots.append(TimeSlot(current_time, slot_end, True))
            
            current_time = slot_end

        return available_slots

    finally:
        cursor.close()
        conn.close()

# 患者信息相关工具
@tool
def fetch_patient_info(*, config: RunnableConfig) -> dict:
    """Fetch patient's basic information and recent medical records"""
    configuration = config.get("configurable", {})
    patient_id = configuration.get("patient_id")
    if not patient_id:
        raise ValueError("No patient ID configured.")

    conn = sqlite3.connect('hospital.sqlite')
    cursor = conn.cursor()

    try:
        # Get patient basic info
        cursor.execute('''
            SELECT * FROM patients WHERE patient_id = ?
        ''', (patient_id,))
        patient_info = cursor.fetchone()
        if not patient_info:
            return {"error": "Patient not found"}

        # Get recent appointments
        cursor.execute('''
            SELECT a.*, d.name as doctor_name, dep.name as department_name
            FROM appointments a
            JOIN doctors d ON a.doctor_id = d.doctor_id
            JOIN departments dep ON a.department_id = dep.department_id
            WHERE a.patient_id = ?
            ORDER BY a.scheduled_time DESC
            LIMIT 5
        ''', (patient_id,))
        appointments = cursor.fetchall()

        # Get recent medical records
        cursor.execute('''
            SELECT m.*, d.name as doctor_name
            FROM medical_records m
            JOIN doctors d ON m.doctor_id = d.doctor_id
            WHERE m.patient_id = ?
            ORDER BY m.visit_date DESC
            LIMIT 5
        ''', (patient_id,))
        records = cursor.fetchall()

        return {
            "patient_info": dict(zip(
                ["patient_id", "name", "birth_date", "gender", "phone", "email", 
                 "address", "emergency_contact", "blood_type", "allergies", 
                 "created_at", "last_visit_date"], 
                patient_info)),
            "recent_appointments": [dict(zip(
                ["appointment_id", "patient_id", "doctor_id", "department_id", 
                 "scheduled_time", "end_time", "appointment_type", "status", 
                 "notes", "symptoms", "created_at", "last_updated", 
                 "cancelled_reason", "doctor_name", "department_name"], 
                appt)) for appt in appointments],
            "recent_records": [dict(zip(
                ["record_id", "patient_id", "doctor_id", "visit_date", 
                 "chief_complaint", "diagnosis", "treatment", "prescriptions",
                 "lab_results", "follow_up_notes", "next_appointment", 
                 "created_at", "doctor_name"], 
                record)) for record in records]
        }
    finally:
        cursor.close()
        conn.close()

# 科室查询工具
@tool
def search_departments(
    name: Optional[str] = None,
    is_active: bool = True
) -> list[dict]:
    """Search for hospital departments"""
    conn = sqlite3.connect('hospital.sqlite')
    cursor = conn.cursor()

    try:
        query = "SELECT * FROM departments WHERE 1=1"
        params = []

        if name:
            query += " AND name LIKE ?"
            params.append(f"%{name}%")
        
        if is_active:
            query += " AND is_active = 1"

        cursor.execute(query, params)
        departments = cursor.fetchall()

        return [dict(zip(
            ["department_id", "name", "description", "location", 
             "contact_number", "working_hours", "is_active"],
            dept)) for dept in departments]
    finally:
        cursor.close()
        conn.close()

# 医生查询工具
@tool
def search_doctors(
    department: Optional[str] = None,
    name: Optional[str] = None,
    specialty: Optional[str] = None,
    is_active: bool = True
) -> list[dict]:
    """Search for doctors based on various criteria"""
    conn = sqlite3.connect('hospital.sqlite')
    cursor = conn.cursor()

    try:
        query = """
            SELECT d.*, dep.name as department_name 
            FROM doctors d
            JOIN departments dep ON d.department_id = dep.department_id 
            WHERE 1=1
        """
        params = []

        if department:
            query += " AND dep.name LIKE ?"
            params.append(f"%{department}%")
        
        if name:
            query += " AND d.name LIKE ?"
            params.append(f"%{name}%")
        
        if specialty:
            query += " AND d.specialty LIKE ?"
            params.append(f"%{specialty}%")
        
        if is_active:
            query += " AND d.is_active = 1"

        cursor.execute(query, params)
        doctors = cursor.fetchall()

        return [dict(zip(
            ["doctor_id", "name", "department_id", "title", "specialty", 
             "working_days", "working_hours", "max_daily_appointments", 
             "email", "contact_number", "is_active", "department_name"],
            doc)) for doc in doctors]
    finally:
        cursor.close()
        conn.close()

# 预约相关工具
@tool
def search_available_appointments(
    department: Optional[str] = None,
    doctor_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> list[dict]:
    """Search for available appointment slots"""
    conn = sqlite3.connect('hospital.sqlite')
    cursor = conn.cursor()

    try:
        # Build query to get relevant doctors
        query = """
            SELECT d.doctor_id, d.name, d.specialty, d.working_days, d.working_hours,
                   dep.name as department_name
            FROM doctors d
            JOIN departments dep ON d.department_id = dep.department_id
            WHERE d.is_active = 1
        """
        params = []

        if department:
            query += " AND dep.name LIKE ?"
            params.append(f"%{department}%")
        
        if doctor_id:
            query += " AND d.doctor_id = ?"
            params.append(doctor_id)

        cursor.execute(query, params)
        doctors = cursor.fetchall()

        # For each doctor, get available slots
        available_appointments = []
        current_date = start_date or datetime.now()
        end_date = end_date or (current_date + timedelta(days=7))

        for doctor in doctors:
            doctor_id = doctor[0]
            while current_date <= end_date:
                slots = get_available_slots(doctor_id, current_date)
                for slot in slots:
                    available_appointments.append({
                        "doctor_id": doctor_id,
                        "doctor_name": doctor[1],
                        "specialty": doctor[2],
                        "department": doctor[5],
                        "date": slot.start_time.strftime('%Y-%m-%d'),
                        "start_time": slot.start_time.strftime('%H:%M'),
                        "end_time": slot.end_time.strftime('%H:%M')
                    })
                current_date += timedelta(days=1)

        return available_appointments

    finally:
        cursor.close()
        conn.close()

@tool
def book_appointment(
    doctor_id: int,
    scheduled_time: datetime,
    appointment_type: str,
    symptoms: str,
    *,
    config: RunnableConfig
) -> str:
    """Book an appointment with enhanced validation"""
    configuration = config.get("configurable", {})
    patient_id = configuration.get("patient_id")
    if not patient_id:
        raise ValueError("No patient ID configured.")

    conn = sqlite3.connect('hospital.sqlite')
    cursor = conn.cursor()

    try:
        # Validate appointment time
        is_valid, message = validate_appointment_time(doctor_id, scheduled_time)
        if not is_valid:
            return f"Cannot book appointment: {message}"

        # Get doctor's department
        cursor.execute('SELECT department_id FROM doctors WHERE doctor_id = ?', (doctor_id,))
        doctor = cursor.fetchone()
        if not doctor:
            return "Doctor not found."

        department_id = doctor[0]
        end_time = scheduled_time + timedelta(minutes=30)  # 30-minute appointments

        # Create appointment
        cursor.execute('''
            INSERT INTO appointments (
                patient_id, doctor_id, department_id, scheduled_time, end_time,
                appointment_type, symptoms, created_at, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ''', (patient_id, doctor_id, department_id, 
              scheduled_time.strftime('%Y-%m-%d %H:%M:%S'),
              end_time.strftime('%Y-%m-%d %H:%M:%S'),
              appointment_type, symptoms))
        
        appointment_id = cursor.lastrowid
        conn.commit()

        return f"Appointment successfully booked! Appointment ID: {appointment_id}"

    except Exception as e:
        conn.rollback()
        return f"Failed to book appointment: {str(e)}"
    finally:
        cursor.close()
        conn.close()

@tool
def update_appointment(
    appointment_id: int,
    new_time: Optional[datetime] = None,
    new_doctor_id: Optional[int] = None,
    *,
    config: RunnableConfig
) -> str:
    """Update an existing appointment"""
    configuration = config.get("configurable", {})
    patient_id = configuration.get("patient_id")
    if not patient_id:
        raise ValueError("No patient ID configured.")

    conn = sqlite3.connect('hospital.sqlite')
    cursor = conn.cursor()

    try:
        # Verify appointment exists and belongs to patient
        cursor.execute('''
            SELECT status FROM appointments 
            WHERE appointment_id = ? AND patient_id = ?
        ''', (appointment_id, patient_id))
        
        result = cursor.fetchone()
        if not result:
            return "Appointment not found or does not belong to current patient."
        
        if result[0] != 'scheduled':
            return "Cannot modify completed or cancelled appointments."

        updates = []
        params = []
        
        if new_time:
            if new_doctor_id:
                is_valid, message = validate_appointment_time(new_doctor_id, new_time)
            else:
                cursor.execute('SELECT doctor_id FROM appointments WHERE appointment_id = ?', 
                             (appointment_id,))
                current_doctor_id = cursor.fetchone()[0]
                is_valid, message = validate_appointment_time(current_doctor_id, new_time)
            
            if not is_valid:
                return f"Invalid new appointment time: {message}"
                
            updates.extend(["scheduled_time = ?", "end_time = ?"])
            params.extend([
                new_time.strftime('%Y-%m-%d %H:%M:%S'),
                (new_time + timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')
            ])
            
        if new_doctor_id:
            cursor.execute('SELECT department_id FROM doctors WHERE doctor_id = ?', 
                         (new_doctor_id,))
            dept = cursor.fetchone()
            if not dept:
                return "Invalid doctor ID"
                
            updates.extend(["doctor_id = ?", "department_id = ?"])
            params.extend([new_doctor_id, dept[0]])

        if not updates:
            return "No changes requested"

        updates.append("last_updated = CURRENT_TIMESTAMP")
        params.extend([appointment_id, patient_id])
        
        query = f'''
            UPDATE appointments 
            SET {', '.join(updates)}
            WHERE appointment_id = ? AND patient_id = ?
        '''
        
        cursor.execute(query, params)
        conn.commit()

        return "Appointment successfully updated"

    except Exception as e:
        conn.rollback()
        return f"Failed to update appointment: {str(e)}"
    finally:
        cursor.close()
        conn.close()

@tool
def cancel_appointment(
    appointment_id: int,
    reason: str,
    *,
    config: RunnableConfig
) -> str:
    """Cancel an existing appointment"""
    configuration = config.get("configurable", {})
    patient_id = configuration.get("patient_id")
    if not patient_id:
        raise ValueError("No patient ID configured.")

    conn = sqlite3.connect('hospital.sqlite')
    cursor = conn.cursor()

    try:
        # Verify appointment exists and belongs to patient
        cursor.execute('''
            SELECT scheduled_time, status 
            FROM appointments 
            WHERE appointment_id = ? AND patient_id = ?
        ''', (appointment_id, patient_id))
        
        result = cursor.fetchone()
        if not result:
            return "Appointment not found or does not belong to current patient."
        
        scheduled_time, status = result
        
        if status != 'scheduled':
            return "Cannot cancel completed or already cancelled appointments."

        # Check cancellation time limit (24 hours before)
        scheduled_dt = datetime.strptime(scheduled_time, '%Y-%m-%d %H:%M:%S')
        if scheduled_dt - datetime.now() < timedelta(hours=24):
            return "Cannot cancel appointments less than 24 hours before scheduled time."

        # Cancel appointment
        cursor.execute('''
            UPDATE appointments 
            SET status = 'cancelled', 
                cancelled_reason = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE appointment_id = ? AND patient_id = ?
        ''', (reason, appointment_id, patient_id))
        
        conn.commit()
        return "Appointment successfully cancelled"

    except Exception as e:
        conn.rollback()
        return f"Failed to cancel appointment: {str(e)}"
    finally:
        cursor.close()
        conn.close()


@tool
def get_upcoming_appointments(*, config: RunnableConfig) -> list[dict]:
    """Get patient's upcoming appointments"""
    configuration = config.get("configurable", {})
    patient_id = configuration.get("patient_id")
    if not patient_id:
        raise ValueError("No patient ID configured.")

    conn = sqlite3.connect('hospital.sqlite')
    cursor = conn.cursor()

    try:
        cursor.execute('''
            SELECT a.*, d.name as doctor_name, dep.name as department_name
            FROM appointments a
            JOIN doctors d ON a.doctor_id = d.doctor_id
            JOIN departments dep ON a.department_id = dep.department_id
            WHERE a.patient_id = ?
            AND a.scheduled_time > CURRENT_TIMESTAMP
            AND a.status = 'scheduled'
            ORDER BY a.scheduled_time ASC
        ''', (patient_id,))
        
        appointments = cursor.fetchall()

        return [dict(zip(
            ["appointment_id", "patient_id", "doctor_id", "department_id", 
             "scheduled_time", "end_time", "appointment_type", "status", 
             "notes", "symptoms", "created_at", "last_updated", 
             "cancelled_reason", "doctor_name", "department_name"],
            appt)) for appt in appointments]
    finally:
        cursor.close()
        conn.close()


@tool
def search_medical_records(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    *,
    config: RunnableConfig
) -> list[dict]:
    """Search patient's medical records within a date range"""
    configuration = config.get("configurable", {})
    patient_id = configuration.get("patient_id")
    if not patient_id:
        raise ValueError("No patient ID configured.")

    conn = sqlite3.connect('hospital.sqlite')
    cursor = conn.cursor()

    try:
        query = """
            SELECT m.*, d.name as doctor_name, dep.name as department_name
            FROM medical_records m
            JOIN doctors d ON m.doctor_id = d.doctor_id
            JOIN departments dep ON d.department_id = dep.department_id
            WHERE m.patient_id = ?
        """
        params = [patient_id]

        if start_date:
            query += " AND m.visit_date >= ?"
            params.append(start_date.strftime('%Y-%m-%d'))
        if end_date:
            query += " AND m.visit_date <= ?"
            params.append(end_date.strftime('%Y-%m-%d'))

        query += " ORDER BY m.visit_date DESC"
        
        cursor.execute(query, params)
        records = cursor.fetchall()

        return [dict(zip(
            ["record_id", "patient_id", "doctor_id", "visit_date", 
             "chief_complaint", "diagnosis", "treatment", "prescriptions",
             "lab_results", "follow_up_notes", "next_appointment", 
             "created_at", "doctor_name", "department_name"],
            record)) for record in records]
    finally:
        cursor.close()
        conn.close()


@tool
def submit_doctor_review(
    doctor_id: int,
    rating: int,
    comment: str,
    *,
    config: RunnableConfig
) -> str:
    """Submit a review for a doctor"""
    configuration = config.get("configurable", {})
    patient_id = configuration.get("patient_id")
    if not patient_id:
        raise ValueError("No patient ID configured.")

    if not (1 <= rating <= 5):
        return "Rating must be between 1 and 5"

    conn = sqlite3.connect('hospital.sqlite')
    cursor = conn.cursor()

    try:
        # Verify patient has had an appointment with this doctor
        cursor.execute('''
            SELECT COUNT(*) FROM appointments
            WHERE patient_id = ? AND doctor_id = ? AND status = 'completed'
        ''', (patient_id, doctor_id))
        
        if cursor.fetchone()[0] == 0:
            return "You can only review doctors you have had appointments with"

        # Submit review
        cursor.execute('''
            INSERT INTO doctor_reviews (
                doctor_id, patient_id, rating, comment, created_at
            ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (doctor_id, patient_id, rating, comment))
        
        conn.commit()
        return "Review submitted successfully"

    except Exception as e:
        conn.rollback()
        return f"Failed to submit review: {str(e)}"
    finally:
        cursor.close()
        conn.close()


@tool
def get_medical_expenses(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    *,
    config: RunnableConfig
) -> dict:
    """Get patient's medical expenses summary"""
    configuration = config.get("configurable", {})
    patient_id = configuration.get("patient_id")
    if not patient_id:
        raise ValueError("No patient ID configured.")

    conn = sqlite3.connect('hospital.sqlite')
    cursor = conn.cursor()

    try:
        query = """
            SELECT m.visit_date, m.treatment, m.prescriptions,
                   d.name as doctor_name, dep.name as department_name,
                   b.amount, b.insurance_coverage, b.patient_payment
            FROM medical_records m
            JOIN doctors d ON m.doctor_id = d.doctor_id
            JOIN departments dep ON d.department_id = dep.department_id
            JOIN billing b ON m.record_id = b.record_id
            WHERE m.patient_id = ?
        """
        params = [patient_id]

        if start_date:
            query += " AND m.visit_date >= ?"
            params.append(start_date.strftime('%Y-%m-%d'))
        if end_date:
            query += " AND m.visit_date <= ?"
            params.append(end_date.strftime('%Y-%m-%d'))

        cursor.execute(query, params)
        expenses = cursor.fetchall()

        return {
            "expenses": [dict(zip(
                ["visit_date", "treatment", "prescriptions", "doctor_name",
                 "department_name", "amount", "insurance_coverage", "patient_payment"],
                expense)) for expense in expenses],
            "summary": {
                "total_amount": sum(exp[5] for exp in expenses),
                "total_insurance": sum(exp[6] for exp in expenses),
                "total_patient_payment": sum(exp[7] for exp in expenses)
            }
        }
    finally:
        cursor.close()
        conn.close()