"""
A Dohe poet agent that can compose poetry in the style of traditional Hindi 'Dohe'.
The agent uses a custom model (gpt-oss-20b) locally hosted.
This example demonstrates a single-agent workflow, that is aided by a function tool to ensure the response is always a doha (2 lines, rhyming, moral or philosophical).
A single agent workflow is the simplest workflow, where a single agent is responsible for handling the entire user request with the help of function tools and instructions as needed. The runner executes the agent to get the final output.
"""

from agents import Agent, ModelSettings, function_tool
from openai import AsyncOpenAI

from agents import Agent, OpenAIChatCompletionsModel, Runner, function_tool, set_tracing_disabled

import asyncio


BASE_URL = "http://10.0.0.4:7890/v1" # chat completion endpoint of the locally hosted model
API_KEY = "dummy"  # dummy api key for the locally hosted model
MODEL_NAME = "gpt-oss-20b"  # name of the locally hosted model

# Initialize the custom OpenAI client, model, and agent all locally
client = AsyncOpenAI(base_url=BASE_URL, api_key=API_KEY)
set_tracing_disabled(disabled=True) # Since not providing a valid api key, 

# A function tool to check if a given starting line is a couplet
@function_tool
def check_couplet(couplet: str) -> None:
    """Takes a proposed couplet as input. Check if there are 2 lines."""
    print("Tool Called! checking if the response is a couplet...")
    print("Yes, it is a couplet." if couplet.count('\n') == 1 else "No, it is not a couplet.")

async def main():
    # This agent will use the custom LLM provider
    doha_poet = Agent(
        name="Dohe Poet Agent",
        instructions=(
            "You respond with a doha (couplet) in Hindi (written in Devanagari script) based on the user's input ideas. "
            "A doha is a two-line poem, often with a moral or philosophical message, and should be in the style of classic Hindi poets like Kabir or Rahim. "
            "You must ensure that your response is always a doha (2 lines)."
        ),
        model=OpenAIChatCompletionsModel(model=MODEL_NAME, openai_client=client),
        tools=[check_couplet],
    )
    prompt="Compose a doha."
    print("="*50)
    print(f"**** Prompt: {prompt}")
    result = await Runner.run(doha_poet, prompt)
    print(result)
    print("="*50)
    print(result.final_output)

if __name__ == "__main__":
    asyncio.run(main())