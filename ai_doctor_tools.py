from typing import List, Dict, Optional
from openai import OpenAI
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
import sqlite3
from appointment_tools import *
import json  
import os
from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI()

@tool
def symptom_analysis(
    symptoms: str,
    medical_history: Optional[str] = None,
    *,
    config: RunnableConfig
) -> Dict:
    """
    Analyze patient symptoms and provide initial medical advice
    
    Args:
        symptoms: Patient's current symptoms
        medical_history: Patient's relevant medical history
    """
    try:
        # 构建提示信息
        prompt = f"""As a medical AI assistant, please analyze the following symptoms:
        
Symptoms: {symptoms}
Medical History: {medical_history or 'Not provided'}

Please provide:
1. Possible conditions
2. Severity level (High/Medium/Low)
3. Type of medical expertise needed
4. General advice and self-care recommendations
5. Warning signs to watch for

Format the response as a structured JSON."""

        # 使用新版本的 OpenAI API
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a medical AI assistant helping with initial symptom analysis."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}

        )

        # 解析AI响应
        analysis = json.loads(response.choices[0].message.content)
        print(analysis)
        

        # 组合返回结果
        return {
            "analysis": analysis,
            "recommendations": generate_medical_recommendations(analysis)
        }

    except Exception as e:
        return {"error": f"Failed to analyze symptoms: {str(e)}"}

@tool
def get_patient_medical_history(
    *,
    config: RunnableConfig
) -> Dict:
    """Get patient's medical history"""
    configuration = config.get("configurable", {})
    patient_id = configuration.get("patient_id")
    if not patient_id:
        raise ValueError("No patient ID configured.")

    conn = sqlite3.connect('hospital.sqlite')
    cursor = conn.cursor()

    try:
        # 获取患者基本信息
        cursor.execute('''
            SELECT allergies, chronic_conditions, current_medications, 
                   family_history, past_surgeries
            FROM patients
            WHERE patient_id = ?
        ''', (patient_id,))
        
        patient_info = cursor.fetchone()
        
        # 获取过往就医记录
        cursor.execute('''
            SELECT m.visit_date, m.chief_complaint, m.diagnosis, 
                   m.treatment, m.prescriptions,
                   d.name as doctor_name, dep.name as department_name
            FROM medical_records m
            JOIN doctors d ON m.doctor_id = d.doctor_id
            JOIN departments dep ON d.department_id = dep.department_id
            WHERE m.patient_id = ?
            ORDER BY m.visit_date DESC
        ''', (patient_id,))
        
        medical_records = cursor.fetchall()

        return {
            "patient_info": dict(zip(
                ["allergies", "chronic_conditions", "current_medications",
                 "family_history", "past_surgeries"],
                patient_info
            )),
            "medical_records": [dict(zip(
                ["visit_date", "chief_complaint", "diagnosis", "treatment",
                 "prescriptions", "doctor_name", "department_name"],
                record
            )) for record in medical_records]
        }

    finally:
        cursor.close()
        conn.close()

def generate_medical_recommendations(analysis: Dict) -> List[str]:
    """Generate medical recommendations based on symptom analysis"""
    severity = analysis.get("severity_level", "").lower()
    recommendations = []

    if severity == "high":
        recommendations.extend([
            "🚨 These symptoms require immediate medical attention",
            "Please seek professional medical care as soon as possible",
            "If symptoms worsen, go to the nearest emergency room"
        ])
    elif severity == "medium":
        recommendations.extend([
            "⚠️ These symptoms should be evaluated by a healthcare provider",
            "Consider scheduling a medical consultation",
            "Monitor your symptoms closely"
        ])
    else:
        recommendations.extend([
            "📝 These symptoms can likely be managed with self-care",
            "Monitor your condition over the next few days"
        ])
    return recommendations