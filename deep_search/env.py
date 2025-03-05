import os
from pathlib import Path
from dotenv import load_dotenv

"""
load_dotenv()
print(os.getenv('TAVILY_API_KEY')) 

def load_env():
    # Try to find .env file in current and parent directories
    env_path = Path('.env')
    if not env_path.exists():
        env_path = Path('..env')
        
    if env_path.exists():
        load_dotenv(env_path)
    else:
        print("Warning: .env file not found")

# Load environment variables when module is imported
load_env()

"""

def get_env_or_raise(key: str) -> str:
    """Get environment variable or raise error if not found"""
    value = os.getenv(key)
    if value is None:
        raise ValueError(f"Environment variable {key} not found. Please set it in .env file.")
    return value 