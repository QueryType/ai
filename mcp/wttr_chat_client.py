import asyncio

from agents import Agent, Runner, gen_trace_id, trace
from agents.mcp import MCPServer, MCPServerSse
from agents.model_settings import ModelSettings

# load dotenv
from dotenv import load_dotenv
load_dotenv()

async def run(mcp_server: MCPServer):
    travel_expert_agent = Agent(
        name="Travel Expert Assistant",
        instructions="You are a travel expert.",
        model="gpt-4o",
    )

    wttr_agent = Agent(
        name="wttr Assistant",
        instructions="Use the tools to answer the questions.",
        mcp_servers=[mcp_server],
        model_settings=ModelSettings(tool_choice="required"),
        model="gpt-4o",
    )

    triage_agent = Agent(
        name="Triage Agent",
        instructions="You determine which agent to use based on the user's input.",
        handoffs=[wttr_agent, travel_expert_agent]
    )
    # Test tool call
    while True:
        # Get user input
        message = input("User>> ")
        if message == "exit":
            return "bye"
        else:
            result = await Runner.run(starting_agent=triage_agent, input=message)
            print(f"gpt4o>> {result.final_output}")

async def main():
    async with MCPServerSse(
        name="wttr python mcp sse server",
        params={
            "url": "http://10.0.0.4:7860/sse",
        },
        cache_tools_list=True,
    ) as server:
        trace_id = gen_trace_id()
        with trace(workflow_name="wttr  sse Trace", trace_id=trace_id):
            print(f"View trace: https://platform.openai.com/traces/trace?trace_id={trace_id}\n")
            await run(server)


if __name__ == "__main__":
    asyncio.run(main())
