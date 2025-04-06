from mcp.server.fastmcp import FastMCP

# Create an MCP server instance named "hello"
mcp = FastMCP("hello",host="10.0.0.4", port=7860)

# Define a tool called "hello" that returns a simple greeting
@mcp.tool()
def hello() -> str:
    """Returns a simple greeting."""
    return "Hello, World!"

if __name__ == "__main__":
    # Start the MCP server using stdio transport (ideal for integration with Cursor)
    print("Starting MCP server...")
    mcp.run(transport="sse")    