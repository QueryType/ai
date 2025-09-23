# calculator_mcp_server.py
from fastmcp import FastMCP

# Create MCP server instance
mcp = FastMCP("wttr.in Weather server")

@mcp.tool()
def get_weather(location: str) -> str:
    """
    Fetches current weather information for a specified location using the wttr.in service.
    
    This function makes an HTTP GET request to the wttr.in weather service to retrieve
    weather data in a compact format. The service returns weather information including
    temperature, weather conditions, and other meteorological data.
    
    Args:
        location (str): The location for which to fetch weather data. Can be a city name,
                       airport code, or other location identifier supported by wttr.in.
    
    Returns:
        str: Weather information as a formatted string if successful, or an error message
             if the request fails or an exception occurs.
    
    Raises:
        No exceptions are raised directly - all exceptions are caught and returned as
        error message strings.
    
    Examples:
        >>> get_weather("London")
        "London: ⛅️ +15°C"
        
        >>> get_weather("NYC")
        "New York: ☀️ +22°C"
    
    Note:
        - Requires an active internet connection
        - Uses the wttr.in format=3 parameter for compact output
        - Returns user-friendly error messages for network issues or invalid locations
    """
    """Fetches weather information for a given location using wttr.in service."""
    import requests

    try:
        response = requests.get(f"https://wttr.in/{location}?format=3")
        if response.status_code == 200:
            return response.text
        else:
            return f"Could not fetch weather data for {location}. Please try again."
    except Exception as e:
        return f"An error occurred: {str(e)}"
    

if __name__ == "__main__":
        # Run locally with stdio
        mcp.run(transport="stdio")
