#!/usr/bin/env python3
"""
Entry point to launch the Delta Exchange Model Context Protocol (MCP) Server.
Can be executed directly:
    python run_mcp.py
Or configured in Claude Desktop / Claude Code / Antigravity IDE.
"""

import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.delta_mcp_server import main

if __name__ == "__main__":
    main()
