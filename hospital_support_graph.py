import getpass
import os
from dotenv import load_dotenv
import sqlite3
import datetime
from typing import Optional, List,Literal, Annotated, TypedDict, Callable
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableLambda
from langgraph.prebuilt import ToolNode

from appointment_tools import *
from map_tools import *
from parking_tools import *
from ai_doctor_tools import *

from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.runnables import Runnable, RunnableConfig
from langgraph.graph.message import AnyMessage, add_messages
from langchain_openai import ChatOpenAI

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import tools_condition
from langgraph.checkpoint.memory import MemorySaver

import datetime
from typing import Optional, List
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass
from langchain_core.runnables import RunnableConfig
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field


load_dotenv()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
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
    APPOINTMENT_DURATION = 30 
    
def handle_tool_error(state) -> dict:
    error = state.get("error")
    tool_calls = state["messages"][-1].tool_calls
    return {
        "messages": [
            ToolMessage(
                content=f"Error: {repr(error)}\n please fix your mistakes.",
                tool_call_id=tc["id"],
            )
            for tc in tool_calls
        ]
    }


def create_tool_node_with_fallback(tools: list) -> dict:
    return ToolNode(tools).with_fallbacks(
        [RunnableLambda(handle_tool_error)], exception_key="error"
    )
    

def update_dialog_stack(left: list[str], right: Optional[str]) -> list[str]:
    """Push or pop the state."""
    if right is None:
        return left
    if right == "pop":
        return left[:-1]
    return left + [right]

class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    user_info: str
    dialog_state: Annotated[
        list[Literal["assistant", "appointment", "ai_doctor", "transportation"]],
        update_dialog_stack,
    ]

llm = ChatOpenAI(model="gpt-4o-mini")

# 整合所有工具
hospital_tools = [
    # 预约相关工具
    book_appointment,
    search_doctors,
    update_appointment,
    cancel_appointment,
    get_upcoming_appointments,
    fetch_patient_info,
    search_departments,
    search_doctors,
    search_available_appointments,
    
    get_medical_expenses,
    search_medical_records,

    
    # AI医生工具
    symptom_analysis,
    get_patient_medical_history,
    
    # 交通相关工具
    get_route_to_hospital,
    get_estimated_arrival_time,
    
    # 停车相关工具
    get_parking_availability,
    reserve_parking_spot,
    cancel_parking_reservation,
    
    # 通用搜索工具
    TavilySearchResults(max_results=1)
]

class Assistant:
    def __init__(self, runnable: Runnable):
        self.runnable = runnable

    def __call__(self, state: State, config: RunnableConfig):
        while True:
            configuration = config.get("configurable", {})
            passenger_id = configuration.get("passenger_id", None)
            state = {**state, "user_info": passenger_id}
            result = self.runnable.invoke(state)
            # If the LLM happens to return an empty response, we will re-prompt it
            # for an actual response.
            if not result.tool_calls and (
                not result.content
                or isinstance(result.content, list)
                and not result.content[0].get("text")
            ):
                messages = state["messages"] + [("user", "Respond with a real output.")]
                state = {**state, "messages": messages}
            else:
                break
        return {"messages": result}


# Define CompleteOrEscalate tool
class CompleteOrEscalate(BaseModel):
    """A tool to mark the current task as completed and/or to escalate control of the dialog to the main assistant"""
    cancel: bool = True
    reason: str

    class Config:
        json_schema_extra = {
            "example": {
                "cancel": True,
                "reason": "User changed their mind about the current task.",
            },
            "example 2": {
                "cancel": True,
                "reason": "I have fully completed the task.",
            },
            "example 3": {
                "cancel": False,
                "reason": "I need to search the user's medical records or doctor's schedule for more information.",
            },
        }

# 1. Appointment Assistant
appointment_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a specialized assistant for handling medical appointments. "
        "The primary assistant delegates work to you whenever the user needs to schedule, modify, or cancel medical visits. "
        "Search for available doctors and time slots based on the user's preferences and confirm the appointment details with the user. "
        "If you need more information or the customer changes their mind, escalate the task back to the main assistant. "
        "Remember that a booking isn't completed until after the relevant tool has successfully been used."
        "\n\nIf the user needs help, and none of your tools are appropriate for it, then "
        '"CompleteOrEscalate" the dialog to the host assistant. Do not waste the user\'s time.'
        "\nCurrent time: {time}."
    ),
    ("placeholder", "{messages}"),
]).partial(time=datetime.now)


appointment_safe_tools = [search_doctors, search_departments, search_available_appointments, get_upcoming_appointments]
appointment_sensitive_tools = [book_appointment, update_appointment, cancel_appointment]
appointment_tools = appointment_safe_tools + appointment_sensitive_tools
appointment_runnable = appointment_prompt | llm.bind_tools(appointment_tools + [CompleteOrEscalate])


# 2. AI Doctor Assistant
ai_doctor_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a specialized AI medical assistant for symptom analysis and medical advice. "
        "The primary assistant delegates work to you whenever the user needs symptom analysis or medical record review. "
        "Carefully analyze the user's symptoms, review their medical history, and provide professional advice. "
        "Always maintain a professional and empathetic tone. "
        "If you need more information or the user needs different assistance, escalate the task back to the main assistant."
        "\n\nIf the user needs help, and none of your tools are appropriate for it, then "
        '"CompleteOrEscalate" the dialog to the host assistant. Do not waste the user\'s time.'
        "\nCurrent time: {time}."
    ),
    ("placeholder", "{messages}"),
]).partial(time=datetime.now)

ai_doctor_safe_tools = [symptom_analysis, get_patient_medical_history, search_medical_records]
ai_doctor_runnable = ai_doctor_prompt | llm.bind_tools(ai_doctor_safe_tools + [CompleteOrEscalate])


# 3a. Direction Assistant
direction_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a specialized assistant for handling directions to the hospital. "
        "Help users plan their route to the hospital and provide accurate navigation guidance. "
        "If you need more information or the user needs different assistance, escalate the task back to the main assistant."
        "\n\nIf the user needs help, and none of your tools are appropriate for it, then "
        '"CompleteOrEscalate" the dialog to the host assistant. Do not waste the user\'s time.'
        "\nCurrent time: {time}."
    ),
    ("placeholder", "{messages}"),
]).partial(time=datetime.now)

direction_tools = [get_estimated_arrival_time, get_route_to_hospital]
direction_runnable = direction_prompt | llm.bind_tools(direction_tools + [CompleteOrEscalate])

# 3b. Parking Assistant
parking_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a specialized assistant for handling hospital parking matters. "
        "Help users find parking spots and handle parking reservations. "
        "If you need more information or the user needs different assistance, escalate the task back to the main assistant."
        "\n\nIf the user needs help, and none of your tools are appropriate for it, then "
        '"CompleteOrEscalate" the dialog to the host assistant. Do not waste the user\'s time.'
        "\nCurrent time: {time}."
    ),
    ("placeholder", "{messages}"),
]).partial(time=datetime.now)

parking_safe_tools = [get_parking_availability]
parking_sensitive_tools = [reserve_parking_spot, cancel_parking_reservation]
parking_tools = parking_safe_tools + parking_sensitive_tools
parking_runnable = parking_prompt | llm.bind_tools(parking_tools + [CompleteOrEscalate])

# Update routing tools to include new assistants
class ToAppointmentAssistant(BaseModel):
    """Transfers work to a specialized assistant to handle medical appointments."""
    request: str = Field(description="Any followup questions the appointment assistant should clarify before proceeding.")

class ToAIDoctorAssistant(BaseModel):
    """Transfers work to a specialized AI doctor assistant."""
    symptoms: str = Field(description="The symptoms described by the user")
    request: str = Field(description="Any additional medical-related questions from the user")

    class Config:
        json_schema_extra = {
            "example": {
                "symptoms": "Headache and fever for the past 2 days",
                "request": "I'd like to know if I should see a doctor immediately."
            }
        }

class ToDirectionAssistant(BaseModel):
    """Transfers work to a specialized assistant to handle directions."""
    destination: str = Field(description="The user's destination (typically hospital address:251 E Huron St, Chicago, IL 60611)")
    request: str = Field(description="User's specific needs regarding directions")

    class Config:
        json_schema_extra = {
            "example": {
                "destination": "251 E Huron St, Chicago, IL 60611",
                "request": "I need directions for tomorrow's appointment."
            }
        }

class ToParkingAssistant(BaseModel):
    """Transfers work to a specialized assistant to handle parking matters."""
    request: str = Field(description="User's specific needs regarding parking")

    class Config:
        json_schema_extra = {
            "example": {
                "request": "I need to find and reserve a parking spot for tomorrow's appointment."
            }
        }

# Primary Assistant Prompt
primary_assistant_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a helpful hospital customer support assistant. Your primary role is to answer user queries "
        "and delegate specialized tasks to appropriate assistants:"
        "\n- Hospital Appointments -> Appointment Assistant"
        "\n- Medical Advice -> AI Doctor Assistant"
        "\n- Transportation -> Transportation Assistant"
        "\nThe user is not aware of the different specialized assistants, so do not mention them; "
        "just quietly delegate through function calls."
        "\n\nCurrent patient information:\n<Patient>\n{user_info}\n</Patient>"
        "\nCurrent time: {time}."
        "\n\nWhen searching or using tools, be persistent and thorough. "
        "If a search comes up empty, try expanding your search criteria before giving up."
    ),
    ("placeholder", "{messages}"),
]).partial(time=datetime.now)


# Define the primary assistant's tools and runnable
primary_assistant_tools = [
    ToAppointmentAssistant,
    ToAIDoctorAssistant,
    ToDirectionAssistant,
    ToParkingAssistant,
    # Add any general tools that the primary assistant should have direct access to
    search_medical_records,
    get_medical_expenses,
    TavilySearchResults(max_results=1)
]

# Create the primary assistant's runnable
assistant_runnable = primary_assistant_prompt | llm.bind_tools(
    primary_assistant_tools + [CompleteOrEscalate]
)

# 1. Define State and Entry Node Utility

def create_entry_node(assistant_name: str, new_dialog_state: str) -> Callable:
    """Create an entry node for each specialized workflow."""
    def entry_node(state: State) -> dict:
        tool_call_id = state["messages"][-1].tool_calls[0]["id"]
        return {
            "messages": [
                ToolMessage(
                    content=f"The assistant is now the {assistant_name}. Reflect on the above conversation between the host assistant and the user."
                    f" The user's intent is unsatisfied. Use the provided tools to assist the user. Remember, you are {assistant_name},"
                    " and the action is not complete until after you have successfully invoked the appropriate tool."
                    " If the user changes their mind or needs help for other tasks, call the CompleteOrEscalate function to let the primary host assistant take control."
                    " Do not mention who you are - just act as the proxy for the assistant.",
                    tool_call_id=tool_call_id,
                )
            ],
            "dialog_state": new_dialog_state,
        }
    return entry_node

# 2. Build the Graph
builder = StateGraph(State)

# Initialize user info
def user_info(state: State):
    return {"user_info": fetch_patient_info.invoke({})}

builder.add_node("fetch_user_info", user_info)
builder.add_edge(START, "fetch_user_info")

# 3. Add Appointment Assistant Workflow
builder.add_node(
    "enter_appointment",
    create_entry_node("Medical Appointment Assistant", "appointment")
)
builder.add_node("appointment", Assistant(appointment_runnable))
builder.add_edge("enter_appointment", "appointment")
builder.add_node(
    "appointment_safe_tools",
    create_tool_node_with_fallback(appointment_safe_tools)
)
builder.add_node(
    "appointment_sensitive_tools",
    create_tool_node_with_fallback(appointment_sensitive_tools)
)

def route_appointment(state: State):
    """Route logic for appointment workflow"""
    route = tools_condition(state)
    if route == END:
        return END
    tool_calls = state["messages"][-1].tool_calls
    did_cancel = any(tc["name"] == CompleteOrEscalate.__name__ for tc in tool_calls)
    if did_cancel:
        return "leave_skill"
    safe_toolnames = [t.name for t in appointment_safe_tools]
    if all(tc["name"] in safe_toolnames for tc in tool_calls):
        return "appointment_safe_tools"
    return "appointment_sensitive_tools"

builder.add_edge("appointment_sensitive_tools", "appointment")
builder.add_edge("appointment_safe_tools", "appointment")
builder.add_conditional_edges(
    "appointment",
    route_appointment,
    ["appointment_safe_tools", "appointment_sensitive_tools", "leave_skill", END]
)

# 4. Add AI Doctor Assistant Workflow
builder.add_node(
    "enter_ai_doctor",
    create_entry_node("AI Medical Assistant", "ai_doctor")
)
builder.add_node("ai_doctor", Assistant(ai_doctor_runnable))
builder.add_edge("enter_ai_doctor", "ai_doctor")
builder.add_node(
    "ai_doctor_safe_tools",
    create_tool_node_with_fallback(ai_doctor_safe_tools)
)

def route_ai_doctor(state: State):
    """Route logic for AI doctor workflow"""
    route = tools_condition(state)
    if route == END:
        return END
    tool_calls = state["messages"][-1].tool_calls
    did_cancel = any(tc["name"] == CompleteOrEscalate.__name__ for tc in tool_calls)
    if did_cancel:
        return "leave_skill"
    return "ai_doctor_safe_tools"

builder.add_edge("ai_doctor_safe_tools", "ai_doctor")
builder.add_conditional_edges(
    "ai_doctor",
    route_ai_doctor,
    ["ai_doctor_safe_tools", "leave_skill", END]
)

# 5. Add Direction Assistant Workflow
builder.add_node(
    "enter_direction",
    create_entry_node("Direction Assistant", "direction")
)
builder.add_node("direction", Assistant(direction_runnable))
builder.add_edge("enter_direction", "direction")
builder.add_node(
    "direction_tools",
    create_tool_node_with_fallback(direction_tools)
)

def route_direction(state: State):
    """Route logic for direction workflow"""
    route = tools_condition(state)
    if route == END:
        return END
    tool_calls = state["messages"][-1].tool_calls
    did_cancel = any(tc["name"] == CompleteOrEscalate.__name__ for tc in tool_calls)
    if did_cancel:
        return "leave_skill"
    return "direction_tools"

builder.add_edge("direction_tools", "direction")
builder.add_conditional_edges(
    "direction",
    route_direction,
    ["direction_tools", "leave_skill", END]
)

# 6. Add Parking Assistant Workflow
builder.add_node(
    "enter_parking",
    create_entry_node("Parking Assistant", "parking")
)
builder.add_node("parking", Assistant(parking_runnable))
builder.add_edge("enter_parking", "parking")
builder.add_node(
    "parking_safe_tools",
    create_tool_node_with_fallback(parking_safe_tools)
)
builder.add_node(
    "parking_sensitive_tools",
    create_tool_node_with_fallback(parking_sensitive_tools)
)

def route_parking(state: State):
    """Route logic for parking workflow"""
    route = tools_condition(state)
    if route == END:
        return END
    tool_calls = state["messages"][-1].tool_calls
    did_cancel = any(tc["name"] == CompleteOrEscalate.__name__ for tc in tool_calls)
    if did_cancel:
        return "leave_skill"
    safe_toolnames = [t.name for t in parking_safe_tools]
    if all(tc["name"] in safe_toolnames for tc in tool_calls):
        return "parking_safe_tools"
    return "parking_sensitive_tools"

builder.add_edge("parking_sensitive_tools", "parking")
builder.add_edge("parking_safe_tools", "parking")
builder.add_conditional_edges(
    "parking",
    route_parking,
    ["parking_safe_tools", "parking_sensitive_tools", "leave_skill", END]
)

# 6. Add Primary Assistant and Shared Leave Node
def pop_dialog_state(state: State) -> dict:
    """Pop the dialog stack and return to the main assistant."""
    messages = []
    if state["messages"][-1].tool_calls:
        messages.append(
            ToolMessage(
                content="Resuming dialog with the host assistant. Please reflect on the past conversation and assist the user as needed.",
                tool_call_id=state["messages"][-1].tool_calls[0]["id"],
            )
        )
    return {
        "dialog_state": "pop",
        "messages": messages,
    }

builder.add_node("leave_skill", pop_dialog_state)
builder.add_edge("leave_skill", "primary_assistant")

# Add primary assistant
builder.add_node("primary_assistant", Assistant(assistant_runnable))
builder.add_node(
    "primary_assistant_tools",
    create_tool_node_with_fallback(primary_assistant_tools)
)

def route_primary_assistant(state: State):
    """Route logic for primary assistant"""
    route = tools_condition(state)
    if route == END:
        return END
    tool_calls = state["messages"][-1].tool_calls
    if tool_calls:
        if tool_calls[0]["name"] == ToAppointmentAssistant.__name__:
            return "enter_appointment"
        elif tool_calls[0]["name"] == ToAIDoctorAssistant.__name__:
            return "enter_ai_doctor"
        elif tool_calls[0]["name"] == ToDirectionAssistant.__name__:
            return "enter_direction"
        elif tool_calls[0]["name"] == ToParkingAssistant.__name__:
            return "enter_parking"
        return "primary_assistant_tools"
    raise ValueError("Invalid route")

builder.add_conditional_edges(
    "primary_assistant",
    route_primary_assistant,
    [
        "enter_appointment",
        "enter_ai_doctor",
        "enter_direction",
        "enter_parking",
        "primary_assistant_tools",
        END,
    ]
)
builder.add_edge("primary_assistant_tools", "primary_assistant")

# 7. Add routing logic for user responses
def route_to_workflow(state: State) -> Literal[
    "primary_assistant",
    "appointment",
    "ai_doctor",
    "direction",
    "parking"
]:
    """Route to appropriate workflow based on dialog state"""
    dialog_state = state.get("dialog_state")
    if not dialog_state:
        return "primary_assistant"
    return dialog_state[-1]

builder.add_conditional_edges("fetch_user_info", route_to_workflow)

# 8. Compile the graph
memory = MemorySaver()
hospital_support_graph = builder.compile(
    checkpointer=memory,
    interrupt_before=[
        "appointment_sensitive_tools",
        "parking_sensitive_tools"
    ]
)

# Make the graph available for import
__all__ = ["hospital_support_graph"]