"""EchoMind Band agents package.

Each agent is a standalone runnable Python script that connects to Band
via WebSocket using the GoogleADKAdapter. The Flask app does not import
these — they run as separate processes alongside the web server.
"""