import asyncio
import os
from dataclasses import dataclass
from typing import List, Optional
from PyPDF2 import PdfReader
import docx

import gradio as gr
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from browser_use import Agent
from pydantic import SecretStr
from browser_use.browser.browser import Browser, BrowserConfig
from browser_use.controller.service import Controller

load_dotenv()
#api_key = os.getenv('OPENAI_API_KEY', '')
api_key = os.getenv('Deepseek_API_KEY', '')

@dataclass
class ActionResult:
	is_done: bool
	extracted_content: Optional[str]
	error: Optional[str]
	include_in_memory: bool


@dataclass
class AgentHistoryList:
	all_results: List[ActionResult]
	all_model_outputs: List[dict]


def parse_agent_history(history_str: str) -> None:
	console = Console()

	# Split the content into sections based on ActionResult entries
	sections = history_str.split('ActionResult(')

	for i, section in enumerate(sections[1:], 1):  # Skip first empty section
		# Extract relevant information
		content = ''
		if 'extracted_content=' in section:
			content = section.split('extracted_content=')[1].split(',')[0].strip("'")

		if content:
			header = Text(f'Step {i}', style='bold blue')
			panel = Panel(content, title=header, border_style='blue')
			console.print(panel)
			console.print()


def read_file_content(file_obj) -> str:
	"""读取上传的文件内容"""
	if file_obj is None:
		return ""
		
	file_path = file_obj.name
	content = ""
	
	if file_path.endswith('.pdf'):
		pdf = PdfReader(file_path)
		for page in pdf.pages:
			content += page.extract_text() or ''
	elif file_path.endswith(('.doc', '.docx')):
		doc = docx.Document(file_path)
		content = "\n".join([paragraph.text for paragraph in doc.paragraphs])
	else:
		with open(file_path, 'r', encoding='utf-8') as f:
			content = f.read()
			
	return content


async def run_browser_task(
	task: str,
	model: str = 'gpt-4o-mini',
	headless: bool = True,
	file_obj = None,
) -> str:
	# Get API key based on model selection
	if 'deepseek' in model.lower():
		api_key = os.getenv('DEEPSEEK_API_KEY', '')
		if not api_key.strip():
			return 'Error: DEEPSEEK_API_KEY not found in environment variables'
		llm = ChatOpenAI(
			base_url='https://api.deepseek.com',
			model='deepseek-chat',
			api_key=SecretStr(api_key),
			model_kwargs={
				"messages_to_dict": lambda x: {
					"role": x.role,
					"content": x.content
				}
			}
		)
	else:
		api_key = os.getenv('OPENAI_API_KEY', '')
		if not api_key.strip():
			return 'Error: OPENAI_API_KEY not found in environment variables'
		llm = ChatOpenAI(model=model)

	try:
		controller = Controller()
		browser = Browser(
			config=BrowserConfig(
				headless=headless
			)
		)

		# 如果有上传文件，添加文件内容到任务描述中
		if file_obj:
			file_content = read_file_content(file_obj)
			task = f"Here is the content of my file for reference:\n{file_content}\n\nTask: {task}"
		
		agent = Agent(
			task=task,
			llm=llm,
			controller=controller,
			browser=browser,
			use_vision=True,
			max_actions_per_step=1,
		)
		
		history = await agent.run()
		await browser.close()
		
		# 提取最终结果
		final_result = ""
		if history and history.history:
			for item in reversed(history.history):
				if item.result:
					for result in item.result:
						if result.extracted_content:
							final_result = result.extracted_content
							break
					if final_result:
						break
		
		if not final_result:
			final_result = "Task completed but no specific output was generated."
			
		return final_result

	except Exception as e:
		return f'Error: {str(e)}'


def create_ui():
	with gr.Blocks(title='Browser Use GUI') as interface:
		gr.Markdown('# Browser Use Task Automation')

		with gr.Row():
			with gr.Column():
				task = gr.Textbox(
					label='Task Description',
					placeholder='E.g., Find flights from New York to London for next week',
					lines=3,
				)
				file_upload = gr.File(
					label="Upload File (Optional)",
					file_types=[".pdf", ".doc", ".docx", ".txt"],
				)
				model = gr.Dropdown(
					choices=['gpt-4o-mini', 'gpt-3.5-turbo', 'deepseek-chat'], 
					label='Model', 
					value='gpt-4o-mini'
				)
				headless = gr.Checkbox(label='Run Headless', value=True)
				submit_btn = gr.Button('Run Task')

			with gr.Column():
				output = gr.Textbox(label='Output', lines=10, interactive=False)

		submit_btn.click(
			fn=lambda *args: asyncio.run(run_browser_task(*args)),
			inputs=[task, model, headless, file_upload],
			outputs=output,
		)

	return interface


if __name__ == '__main__':
	demo = create_ui()
	demo.launch()