from .graph import graph
from .configuration import Configuration, LLMProvider, SearchAPI

def get_user_input():
    """Get user input for research topic and model selection"""
    print("\n=== Research Assistant Configuration ===")
    
    # Get research topic
    research_topic = input("\nEnter your research topic: ").strip()
    while not research_topic:
        research_topic = input("Topic cannot be empty, please try again: ").strip()

    # Select LLM provider
    print("\nAvailable LLM models:")
    print("1. DeepSeek")
    print("2. GPT")
    
    while True:
        llm_choice = input("\nSelect LLM model (enter 1-2): ").strip()
        if llm_choice == "1":
            llm_provider = LLMProvider.DEEPSEEK.value
            break
        elif llm_choice == "2":
            llm_provider = LLMProvider.GPT.value
            break
        else:
            print("Invalid choice, please try again")

    # Select search API
    print("\nAvailable Search APIs:")
    print("1. Tavily")
    print("2. Perplexity")
    
    while True:
        search_choice = input("\nSelect Search API (enter 1-2): ").strip()
        if search_choice == "1":
            search_api = SearchAPI.TAVILY.value
            break
        elif search_choice == "2":
            search_api = SearchAPI.PERPLEXITY.value
            break
        else:
            print("Invalid choice, please try again")

    # Set research loop count
    while True:
        try:
            loops = int(input("\nEnter number of research loops (recommended 1-5): ").strip())
            if 1 <= loops <= 10:
                break
            else:
                print("Please enter a number between 1-10")
        except ValueError:
            print("Please enter a valid number")

    return research_topic, llm_provider, search_api, loops

def main():
    """Main function"""
    print("Welcome to Research Assistant!")
    print("This assistant will help you research a specific topic by automatically searching and summarizing relevant information.")
    
    # Get user input
    research_topic, llm_provider, search_api, max_loops = get_user_input()
    
    # Configure research assistant
    config = {
        "configurable": {
            "llm_provider": llm_provider,
            "search_api": search_api,
            "max_web_research_loops": max_loops
        }
    }

    print("\n=== Starting Research ===")
    print(f"Research Topic: {research_topic}")
    print(f"Using Model: {llm_provider}")
    print(f"Using Search: {search_api}")
    print(f"Research Loops: {max_loops}")
    print("\nConducting research, please wait...\n")

    try:
        # Run research
        result = graph.invoke(
            {"research_topic": research_topic},
            config=config
        )

        # Print results
        print("\n=== Research Results ===")
        print(result["running_summary"])
        
    except Exception as e:
        print(f"\nAn error occurred during research: {str(e)}")
        print("Please ensure all necessary API keys are properly set.")

if __name__ == "__main__":
    main() 