from flask import Flask, render_template, request, jsonify, redirect
import uuid
from hospital_support_graph import hospital_support_graph
import time
import requests
from multiagent import MedicalDiagnosisCrew  # Import your existing multiagent class
from browser import run_browser_task  # Import the browser task function
import asyncio
import tempfile
import os
# Add deep search imports
from deep_search.graph import graph as deep_search_graph
from deep_search.configuration import Configuration, LLMProvider, SearchAPI

app = Flask(__name__)

# Store session states
sessions = {}

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/redirect_to_gradio')
def redirect_to_gradio():
    return redirect("https://2a44bb1a28317d2c8b.gradio.live")

@app.route('/analyze_image', methods=['POST'])
def analyze_image():
    if 'image' not in request.files:
        return jsonify({"error": "No image provided"})
    
    image = request.files['image']
    session_id = request.form.get('session_id')
    prompt = request.form.get('prompt', '').strip()
    
    if not session_id:
        session_id = str(uuid.uuid4())
        # ... (initialize session if needed)
    
    try:
        # Send image to Gradio endpoint
        gradio_url = "https://2a44bb1a28317d2c8b.gradio.live/predict"
        files = {'image': (image.filename, image.read(), image.content_type)}
        response = requests.post(gradio_url, files=files)
        
        if response.status_code == 200:
            analysis_result = response.json()
            analysis_text = analysis_result['prediction']
            
            # If there's a prompt, include it in the response
            if prompt:
                analysis_text = f"Regarding your question: '{prompt}'\n\nAnalysis: {analysis_text}"
            
            return jsonify({
                "session_id": session_id,
                "analysis": analysis_text
            })
        else:
            return jsonify({
                "session_id": session_id,
                "error": "Failed to analyze image"
            })
            
    except Exception as e:
        return jsonify({
            "session_id": session_id,
            "error": f"Error analyzing image: {str(e)}"
        })


@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    message = data.get('message', '').strip()
    session_id = data.get('session_id')
    
    # Fix: Handle null or invalid session_id
    if not session_id or session_id == 'null':
        session_id = str(uuid.uuid4())
        patient_id = str(uuid.uuid4())
        sessions[session_id] = {
            "printed": set(),
            "config": {
                "configurable": {
                    "patient_id": patient_id,
                    "thread_id": session_id,
                }
            }
        }
    elif session_id not in sessions:
        patient_id = str(uuid.uuid4())
        sessions[session_id] = {
            "printed": set(),
            "config": {
                "configurable": {
                    "patient_id": patient_id,
                    "thread_id": session_id,
                }
            }
        }
    
    if not message:
        return jsonify({"error": "Empty message"})
    
    try:
        session = sessions[session_id]
        events = hospital_support_graph.stream(
            {"messages": ("user", message)},
            session["config"],
            stream_mode="values"
        )
        
        responses = []
        for event in events:
            current_state = event.get("dialog_state")
            message = event.get("messages")
            
            if message:
                # 处理单个消息或消息列表
                messages_to_process = message if isinstance(message, list) else [message]
                
                for msg in messages_to_process:
                    # 检查是否已经处理过这条消息
                    msg_id = msg.id if hasattr(msg, 'id') else None
                    if msg_id and msg_id in session["printed"]:
                        continue
                    
                    # 获取消息内容
                    content = msg.content if hasattr(msg, 'content') else str(msg)
                    
                    # 如果消息有工具调用，确保它们被正确处理
                    if hasattr(msg, 'tool_calls') and msg.tool_calls:
                        for tool_call in msg.tool_calls:
                            # 添加工具调用响应
                            tool_response = {
                                'tool_call_id': tool_call['id'],
                                'content': content
                            }
                            responses.append(tool_response)
                    else:
                        # 普通消息直接添加到响应中
                        responses.append(content)
                    
                    # 标记消息为已处理
                    if msg_id:
                        session["printed"].add(msg_id)
        
        return jsonify({
            "session_id": session_id,
            "responses": responses
        })
        
    except Exception as e:
        print(f"Error in chat endpoint: {str(e)}")  # Add logging
        return jsonify({
            "session_id": session_id,
            "error": "An error occurred while processing your message. Please try again."
        }), 500

@app.route('/run_diagnosis', methods=['POST'])
def run_diagnosis():
    try:
        data = request.json
        
        # Format patient case
        patient_case = f"""
        Patient Information:
        {data['basic_info']}
        
        Presenting Complaints:
        {data['symptoms']}
        
        Medical History:
        {data['medical_history']}
        
        Current Medications:
        {data['medications']}
        
        Vital Signs:
        {data['vital_signs']}
        """
        
        # Initialize medical diagnosis crew
        crew = MedicalDiagnosisCrew(model_name="gpt-4o-mini", temperature=0.7)
        
        # Run diagnosis and convert result to string
        diagnosis_result = str(crew.run_diagnosis(patient_case))
        
        # Create a simple diagnosis process with the result
        diagnosis_process = [{
            "specialist": "Medical Team",
            "message": diagnosis_result
        }]
        
        return jsonify({
            "success": True,
            "diagnosis_process": diagnosis_process
        })
        
    except Exception as e:
        print(f"Diagnosis error: {str(e)}")  # Add logging
        return jsonify({
            "error": f"Error during diagnosis: {str(e)}"
        }), 500

@app.route('/run_browser_task', methods=['POST'])
def browser_task():
    try:
        task = request.form.get('task')
        model = request.form.get('model', 'gpt-4o-mini')
        headless = request.form.get('headless', 'true').lower() == 'true'
        
        if not task:
            return jsonify({"error": "No task provided"})
        
        file = request.files.get('file')
        
        # 如果有文件，创建临时文件
        temp_file = None
        if file:
            # 获取文件扩展名
            file_ext = os.path.splitext(file.filename)[1]
            
            # 创建临时文件
            temp_file = tempfile.NamedTemporaryFile(suffix=file_ext, delete=False)
            file.save(temp_file.name)
            temp_file.close()
            
        try:
            result = asyncio.run(run_browser_task(
                task=task,
                model=model,
                headless=headless,
                file_obj=temp_file if file else None
            ))
            
            return jsonify({
                "success": True,
                "result": result
            })
            
        finally:
            # 清理临时文件
            if temp_file:
                try:
                    os.unlink(temp_file.name)
                except:
                    pass
        
    except Exception as e:
        print(f"Browser task error: {str(e)}")  # Add logging
        return jsonify({
            "error": f"Error during browser task: {str(e)}"
        }), 500

@app.route('/deep_search', methods=['POST'])
def deep_search():
    try:
        data = request.json
        research_topic = data.get('research_topic')
        llm_provider = data.get('llm_provider')
        search_api = data.get('search_api')
        max_loops = data.get('max_loops', 3)
        
        if not research_topic:
            return jsonify({"error": "Research topic is required"})
            
        config = {
            "configurable": {
                "llm_provider": llm_provider,
                "search_api": search_api,
                "max_web_research_loops": max_loops
            }
        }
        
        # 运行研究 - 使用正确导入的 deep_search_graph
        result = deep_search_graph.invoke(
            {"research_topic": research_topic},
            config=config
        )
        
        return jsonify({
            "success": True,
            "result": result["running_summary"]
        })
        
    except Exception as e:
        print(f"Deep search error: {str(e)}")
        return jsonify({
            "error": f"Error during research: {str(e)}"
        }), 500

if __name__ == '__main__':
    app.run(debug=True)