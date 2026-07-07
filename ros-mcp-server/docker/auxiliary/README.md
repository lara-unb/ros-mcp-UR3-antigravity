# Auxiliary Docker for Gemini + ROS MCP

This setup provides a container with:
- **Gemini CLI**: The interface to interact with the LLM.
- **ROS MCP Server**: The bridge between Gemini and ROS.

It is designed to work as an auxiliary container alongside a URSim (Universal Robots Simulator) instance.

## Prerequisites

- Docker and Docker Compose installed.
- A **Gemini API Key**. You can get one at [Google AI Studio](https://aistudio.google.com/).

## Setup

1. **Set your API Key**:
   Export your API key in your terminal:
   ```bash
   export GEMINI_API_KEY="your_api_key_here"
   ```

2. **Build and Run**:
   From this directory (`docker/auxiliary`), run:
   ```bash
   docker-compose run gemini-mcp
   ```

## Connecting to URSim

The container uses `network_mode: host` by default. This means it can reach URSim if it's running on the same machine and has ports mapped to the host (e.g., 9090 for rosbridge).

Once inside the Gemini CLI, you can tell it to connect:

> "Conecte ao robô no localhost na porta 9090"

Gemini will use the `ros-mcp-server` to discover topics, services, and actions available in the URSim environment.

## Usage with UR3 Scripts

Since this container has the `robot_specifications` mapped as a volume, you can add your UR3 specific prompts or configurations to `robot_specifications/` on your host, and they will be available to the MCP server.
