from crewai import Agent, Task, Crew, Process
from langchain_openai import ChatOpenAI
from typing import Dict
import os
import dotenv

dotenv.load_dotenv()

class MedicalDiagnosisCrew:
    def __init__(self, model_name: str = "gpt-4o-mini", temperature: float = 0.7):
        """
        Initialize the Medical Diagnosis Crew with customizable LLM parameters.
        
        Args:
            model_name (str): The name of the LLM model to use
            temperature (float): The temperature parameter for the LLM
        """
        self.llm = ChatOpenAI(
            model_name=model_name,
            temperature=temperature,
            api_key=os.getenv("OPENAI_API_KEY")
        )
        self._initialize_agents()
    
    def _initialize_agents(self):
        """Initialize all medical agents with their respective roles and expertise."""
        self.triage_agent = self._create_triage_agent()
        self.specialist_agents = self._create_specialist_agents()
    
    def _create_triage_agent(self) -> Agent:
        """Create the triage agent with specific role and expertise."""
        return Agent(
            role='Medical Triage Specialist',
            goal='Analyze patient cases and determine which medical specialists are needed',
            backstory="""You are an experienced medical triage specialist with extensive knowledge 
            across medical fields. Your role is to analyze patient cases and determine which types 
            of specialists would be most appropriate for consultation.""",
            verbose=True,
            allow_delegation=False,
            llm=self.llm
        )
    
    def _create_specialist_agents(self) -> Dict[str, Agent]:
        """Create all specialist agents with their respective roles and expertise."""
        self.specialists = {
            'chief_medical_officer': {
                'role': 'Chief Medical Officer',
                'goal': 'Coordinate medical team and synthesize final diagnosis',
                'backstory': """You are the Chief Medical Officer responsible for coordinating 
                the medical team and synthesizing their findings into a final diagnosis."""
            },
            'internist': {
                'role': 'Internal Medicine Specialist',
                'goal': 'Provide comprehensive internal medicine evaluation',
                'backstory': """You are an experienced internist who specializes in complex 
                medical conditions and their interrelationships."""
            },
            'cardiologist': {
                'role': 'Cardiologist',
                'goal': 'Evaluate cardiovascular aspects of the case',
                'backstory': """You are a cardiologist specialized in heart and vascular conditions, 
                with expertise in both preventive cardiology and acute cardiac care."""
            },
            'neurologist': {
                'role': 'Neurologist',
                'goal': 'Evaluate neurological conditions and symptoms',
                'backstory': """You are a neurologist specialized in disorders of the nervous system, 
                including the brain, spinal cord, peripheral nerves, and muscles."""
            },
            'endocrinologist': {
                'role': 'Endocrinologist',
                'goal': 'Evaluate hormonal and metabolic disorders',
                'backstory': """You are an endocrinologist specialized in hormone-related conditions, 
                diabetes, thyroid disorders, and other metabolic diseases."""
            },
            'nephrologist': {
                'role': 'Nephrologist',
                'goal': 'Evaluate kidney function and related disorders',
                'backstory': """You are a nephrologist specialized in kidney diseases, hypertension, 
                and fluid/electrolyte disorders."""
            },
            'pulmonologist': {
                'role': 'Pulmonologist',
                'goal': 'Evaluate respiratory system and lung conditions',
                'backstory': """You are a pulmonologist specialized in diseases of the respiratory 
                system, including the lungs, upper airways, and chest cavity."""
            },
            'gastroenterologist': {
                'role': 'Gastroenterologist',
                'goal': 'Evaluate digestive system disorders',
                'backstory': """You are a gastroenterologist specialized in diseases of the digestive 
                system, including the esophagus, stomach, intestines, liver, and pancreas."""
            },
            'rheumatologist': {
                'role': 'Rheumatologist',
                'goal': 'Evaluate autoimmune and musculoskeletal conditions',
                'backstory': """You are a rheumatologist specialized in autoimmune diseases, 
                arthritis, and other disorders affecting joints, muscles, and bones."""
            },
            'infectious_disease': {
                'role': 'Infectious Disease Specialist',
                'goal': 'Evaluate infectious diseases and complex infections',
                'backstory': """You are an infectious disease specialist with expertise in diagnosing 
                and treating complex infections, including bacterial, viral, fungal, and parasitic infections."""
            },
            'psychiatrist': {
                'role': 'Psychiatrist',
                'goal': 'Evaluate mental health aspects and neuropsychiatric conditions',
                'backstory': """You are a psychiatrist specialized in mental health conditions, 
                behavioral disorders, and the intersection of physical and mental health."""
            }
        }
        
        return {
            key: Agent(
                role=spec['role'],
                goal=spec['goal'],
                backstory=spec['backstory'],
                verbose=True,
                allow_delegation=key == 'chief_medical_officer',
                llm=self.llm
            )
            for key, spec in self.specialists.items()
        }

    def _create_triage_task(self, patient_case: str) -> Task:
        """Create the initial triage task."""
        available_specialists = list(self.specialists.keys())
        return Task(
            description=f"""Analyze the following patient case and determine which medical 
            specialists are needed for proper diagnosis. 
            
            IMPORTANT: You must ONLY select from the following available specialists:
            {', '.join(available_specialists)}
            
            Please return your answer as a comma-separated list of specialist keys.
            For example: "internist,cardiologist,neurologist"
            
            Patient Case:
            {patient_case}""",
            expected_output="A comma-separated list of required specialist keys, selected only from the available specialists list",
            agent=self.triage_agent
        )

    def run_diagnosis(self, patient_case: str) -> str:
        """
        Run the complete medical diagnosis process.
        
        Args:
            patient_case (str): The detailed patient case information
            
        Returns:
            str: The final diagnosis and treatment plan
        """
        # Step 1: Triage
        triage_task = self._create_triage_task(patient_case)
        triage_crew = Crew(
            agents=[self.triage_agent],
            tasks=[triage_task],
            verbose=True,
            process=Process.sequential
        )

        # Get triage results
        triage_result = triage_crew.kickoff()
        triage_result_str = str(triage_result)
        required_specialists = [s.strip() for s in triage_result_str.split(',')]

        # Step 2: Create specialist team and tasks
        selected_agents = {k: self.specialist_agents[k] for k in required_specialists 
                         if k in self.specialist_agents}
        specialist_tasks = []

        # Create tasks for each specialist
        for specialist_key, agent in selected_agents.items():
            task = Task(
                description=f"""Review the patient case and provide your specialist evaluation.
                
                Patient Case:
                {patient_case}
                
                Previous Evaluations:
                {triage_result_str}""",
                expected_output="A detailed medical evaluation from your specialist perspective",
                agent=agent
            )
            specialist_tasks.append(task)

        # Create final synthesis task for CMO
        synthesis_task = Task(
            description=f"""Review all specialist evaluations and provide a final diagnosis 
            and treatment plan.
            
            Patient Case:
            {patient_case}
            
            Specialist Evaluations:
            {{context}}""",
            expected_output="A comprehensive final diagnosis and treatment plan",
            agent=self.specialist_agents['chief_medical_officer']
        )
        specialist_tasks.append(synthesis_task)

        # Create and run the medical crew
        medical_crew = Crew(
            agents=list(selected_agents.values()) + [self.specialist_agents['chief_medical_officer']],
            tasks=specialist_tasks,
            verbose=True,
            process=Process.sequential
        )

        # Return final diagnosis
        return medical_crew.kickoff()

def main():
    """Example usage of the Medical Diagnosis Crew"""
    # Extended Example Patient Case
    patient_case = """
    Patient Information:
    - Name: John Doe
    - Age: 45
    - Gender: Male
    - Ethnicity: White
    - Location: New York, NY
    - BMI: 28.5 (Overweight)
    - Occupation: Office Worker

    Presenting Complaints:
    - Persistent fatigue for 3 months
    - Swelling in lower extremities
    - Difficulty concentrating (brain fog)
    - Increased frequency of urination

    Medical History:
    - Hypertension (diagnosed 5 years ago, poorly controlled)
    - Type 2 Diabetes Mellitus (diagnosed 2 years ago, HbA1c: 8.2%)
    - Family history of chronic kidney disease (mother)

    Current Medications:
    - Lisinopril 20 mg daily
    - Metformin 1000 mg twice daily
    - Atorvastatin 10 mg daily

    Lab Results:
    - eGFR: 59 ml/min/1.73m² (Non-African American)
    - Serum Creatinine: 1.5 mg/dL
    - BUN: 22 mg/dL
    - Potassium: 4.8 mmol/L
    - HbA1c: 8.2%
    - Urinalysis: Microalbuminuria detected (300 mg/g creatinine)

    Vital Signs:
    - Blood Pressure: 145/90 mmHg
    - Heart Rate: 78 bpm
    - Respiratory Rate: 16 bpm
    - Temperature: 98.6°F
    - Oxygen Saturation: 98%
    """
    
    crew = MedicalDiagnosisCrew(model_name="gpt-4", temperature=0.7)
    diagnosis = crew.run_diagnosis(patient_case)
    print("\nFinal Diagnosis:")
    print(diagnosis)

if __name__ == "__main__":
    main() 