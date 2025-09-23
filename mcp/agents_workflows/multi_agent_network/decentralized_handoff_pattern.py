"""
Example of a decentralized multi-agent handoff pattern with bidirectional handoffs between agents.
In this example, we have three agents:
1. Triage Agent: Delegates tasks to the appropriate agents based on the user's request.
2. Weather Agent: Uses the wttr.in service to get accurate and up-to-date weather information.
3. Local Travel Guide Agent: Provides travel-related advisory and places to visit in the area.
Conversation flow:
- The user asks the Triage Agent a question that requires weather information and travel advice.
- The Triage Agent delegates the weather-related part of the query to the Weather Agent.
- The Weather Agent fetches the weather information using the wttr.in MCP server and returns it to the Triage Agent.
- The Triage Agent then delegates the travel-related part of the query to the Local Travel Guide Agent.
- The Local Travel Guide Agent provides travel advice based on the weather information and responds.
"""
import asyncio
import os
from pathlib import Path
from agents import Agent, OpenAIChatCompletionsModel, Runner, gen_trace_id, trace
from openai import AsyncOpenAI

from agents import Agent, Runner
from agents.mcp import MCPServer, MCPServerStdio

# load env variables from a .env file if present
from dotenv import load_dotenv
load_dotenv()

BASE_URL = "http://10.0.0.4:7890/v1" # chat completion endpoint of the locally hosted model
API_KEY = os.getenv("OPENAI_API_KEY")  # set API key only for enabling tracing
MODEL_NAME = "gpt-oss-20b"  # name of the locally hosted model

# Initialize the custom OpenAI client, model, and agent all locally
client = AsyncOpenAI(base_url=BASE_URL, api_key=API_KEY)

async def run(mcp_servers: list[MCPServer]):

    weather_agent = Agent(
        name="Weather Agent",
        model=OpenAIChatCompletionsModel(model=MODEL_NAME, openai_client=client),
        instructions="You are an expert weather agent. You use the wttr.in service to get accurate and up-to-date weather information. " \
        "Use the tools in the MCP server to get the weather information. You will not answer any other questions. Find the location and fetch the weather data. Return the control to the calling agent once you have the information.",
        mcp_servers=mcp_servers
    )

    local_travelguide_agent = Agent(
        name="Local Travel Guide Agent",
        model=OpenAIChatCompletionsModel(model=MODEL_NAME, openai_client=client),
        instructions="You are a travel guide agent. You use appropriate information about weather etc to issue travel-related advisory and places to visit in the area.  Return the control to the calling agent once you have the information."
    )

    triage_agent = Agent(
        name="Triage Agent",
        model=OpenAIChatCompletionsModel(model=MODEL_NAME, openai_client=client),
        instructions="You are a triage agent. Delegate tasks to the appropriate agents based on the user's request. " \
        "Use the weather agent for weather-related queries. " \
        "Use the local travel guide agent for travel-related queries. " \
        "If the user input, asks for both or multiple tasks, internally spilt the prompt in appropriate sub-prompts and delegate to the relevant agents one by one in logical sequence. Combine the responses from the agents to provide a comprehensive answer to the user. Reasoning: high",
        handoffs=[weather_agent, local_travelguide_agent]
    )
    
    # Add bidirectional references - this is the key part
    weather_agent.handoffs.append(triage_agent)
    local_travelguide_agent.handoffs.append(triage_agent)

    # Demo input that should trigger the weather tool from wttr.in server
    prompt="What's the weather in New Delhi today? Is it pleasant to plan a visit to the Red Fort? What other adjoinig places can I visit?"
    print("="*50)
    print(f"**** Prompt: {prompt}")
    result = await Runner.run(starting_agent=triage_agent, input=prompt)
    print(result)
    print("="*50)
    print(result.final_output)

async def main():
    # Path to the wttr.in MCP server script
    weather_script = (Path(__file__).resolve().parent.parent / "mcp" / "wttr-in-mcp.py").resolve()

    # Start the wttr.in MCP server over stdio and pass it to the agent
    async with MCPServerStdio(
        name="wttr.in Weather server",
        params={
            "command": "/opt/miniconda3/envs/mcp/bin/python",
            "args": [str(weather_script)],
        },
    ) as weather_server:
        await run([weather_server])



if __name__ == "__main__":
    trace_id = gen_trace_id()
    with trace(workflow_name="Manager Pattern", trace_id=trace_id):
        asyncio.run(main())