"""
Example of a multi-agent manager pattern where a manager agent delegates tasks to specialized language agents.
In this example, we have four specialized language agents:
1. Portuguese
2. Tamil
3. Swedish
4. Hindi
The manager agent delegates the translation tasks to the appropriate language agents based on the user's request.
Conversation flow:
- The user asks the manager agent to translate a message into multiple languages.
- The manager agent delegates the translation tasks to the appropriate language agents.
- The language agents perform the translations and return the results to the manager agent.
"""
import asyncio
import os
from pathlib import Path
from agents import Agent, OpenAIChatCompletionsModel, Runner, gen_trace_id, trace
from openai import AsyncOpenAI

from agents import Agent, Runner

import asyncio
import os

from dotenv import load_dotenv
load_dotenv()
BASE_URL = "http://10.0.0.4:7890/v1" # chat completion endpoint of the locally hosted model
API_KEY = os.getenv("OPENAI_API_KEY")  # OpenAI API key for enabling tracing
MODEL_NAME = "gpt-oss-20b"  # name of the locally hosted model

# Initialize the custom OpenAI client, model, and agent all locally
client = AsyncOpenAI(base_url=BASE_URL, api_key=API_KEY)

# We define our language agents
portuguese_language_agent = Agent(
    name="Portuguese agent",
    instructions="You translate the user's message to Portuguese",
)

tamil_language_agent = Agent(
    name="Tamil agent",
    instructions="You translate the user's message to Tamil",
)

swedish_language_agent = Agent(
    name="Swedish agent",
    instructions="You translate the user's message to Swedish",
)

hindi_language_agent = Agent(
    name="Hindi agent",
    instructions="You translate the user's message to Hindi",
)

async def main():
    manager_agent = Agent(
        name="Manager agent",
        model=OpenAIChatCompletionsModel(model=MODEL_NAME, openai_client=client),
        instructions="You are a manager agent. You delegate tasks to the appropriate tools based on the user's request. "
        "Use the Portuguese agent tool for Portuguese translations. "
        "Use the Tamil agent tool for Tamil translations. "
        "Use the Swedish agent tool for Swedish translations. "
        "Use the Hindi agent tool for Hindi translations. "
        "Reasoning: high",
        tools = [
            portuguese_language_agent.as_tool(
                tool_name="portuguese_language_agent",
                tool_description="Use this tool to translate the user's message to Portuguese",
            ),
            tamil_language_agent.as_tool(
                tool_name="tamil_language_agent",
                tool_description="Use this tool to translate the user's message to Tamil",
            ),
            swedish_language_agent.as_tool(
                tool_name="swedish_language_agent",
                tool_description="Use this tool to translate the user's message to Swedish",
            ),
            hindi_language_agent.as_tool(
                tool_name="hindi_language_agent",
                tool_description="Use this tool to translate the user's message to Hindi",
            ),
        ]
    )

    prompt="Translate 'World is beautiful, life is a journey.' to Portuguese, Tamil, Swedish and Hindi."
    print("="*50)
    print(f"**** Prompt: {prompt}")
    result = await Runner.run(manager_agent, prompt)
    print(result)
    print("="*50)
    print(result.final_output)


if __name__ == "__main__":
    trace_id = gen_trace_id()
    with trace(workflow_name="Manager Pattern", trace_id=trace_id):
        asyncio.run(main())