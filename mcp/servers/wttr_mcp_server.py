from mcp.server.fastmcp import FastMCP

# Creating a wttr.in MCP server named mywttr.in. 
# This server will fetch weather information from wttr.in.
mcp = FastMCP("mywttr.in",host="10.0.0.4", port=7860)


# Define a tool called "weather" that fetches weather information for a given location
@mcp.tool()
def weather(location: str) -> str:
    """Fetches weather information for a given location as per instructions."""
    import requests

    url = f"https://wttr.in/{location}"
    # Fetch the weather information
    response = requests.get(url)
    
    # Return the response text
    return response.text

if __name__ == "__main__":
    # Start the MCP server
    print("Starting MCP server...")
    mcp.run(transport="sse")    
