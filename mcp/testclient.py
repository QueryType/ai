import asyncio

from agents import Agent, Runner, gen_trace_id, trace
from agents.mcp import MCPServer, MCPServerSse
from agents.model_settings import ModelSettings

# load dotenv
from dotenv import load_dotenv
load_dotenv()

async def run(mcp_server: MCPServer):
    agent = Agent(
        name="Assistant",
        instructions="Use the tools to answer the questions.",
        mcp_servers=[mcp_server],
        model_settings=ModelSettings(tool_choice="required"),
        model="gpt-4o",
    )

    
    # Test tool call
    while True:
        # Get user input
        message = input("User>> ")
        if message == "exit":
            return "bye"
        else:
            #print(f"Running: {message}")
            result = await Runner.run(starting_agent=agent, input=message)
            print(f"gpt4o>> {result.final_output}")

async def main():
    async with MCPServerSse(
        name="wttr.in python mcp sse server",
        params={
            "url": "http://10.0.0.4:7860/sse",
        },
        cache_tools_list=True,
    ) as server:
        trace_id = gen_trace_id()
        with trace(workflow_name="wttr.in  sse Trace", trace_id=trace_id):
            print(f"View trace: https://platform.openai.com/traces/trace?trace_id={trace_id}\n")
            await run(server)


if __name__ == "__main__":
    asyncio.run(main())
