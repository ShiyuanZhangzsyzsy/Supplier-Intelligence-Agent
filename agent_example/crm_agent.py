import json
import os
from anthropic import Anthropic
from pathlib import Path
from tools.crm_tools import (
    add_lead,
    update_status,
    load_crm,
    add_note,
    search_leads,
    delete_lead,
    list_leads_by_status,
    get_lead_details,
)

class CRMAgent:
    def __init__(self, sandbox=None):
        """Initialize agent with optional sandbox for running code."""
        self.sandbox = sandbox
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in .env")
        
        self.client = Anthropic()
        self.conversation_history = []
        
        # Define tools the agent can use
        self.tools = [
            {
                "name": "add_lead",
                "description": "Add a new lead to the CRM",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Lead's full name"},
                        "email": {"type": "string", "description": "Lead's email address"}
                    },
                    "required": ["name", "email"]
                }
            },
            {
                "name": "update_status",
                "description": "Update a lead's status",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "lead_id": {"type": "string", "description": "ID of the lead"},
                        "status": {"type": "string", "description": "New status (e.g., 'new', 'contacted', 'qualified', 'converted')"}
                    },
                    "required": ["lead_id", "status"]
                }
            },
            {
                "name": "list_leads",
                "description": "List all leads in the CRM",
                "input_schema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "add_note",
                "description": "Add a note to a lead",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "lead_id": {"type": "string", "description": "ID of the lead"},
                        "note_text": {"type": "string", "description": "The note text to add"}
                    },
                    "required": ["lead_id", "note_text"]
                }
            },
            {
                "name": "search_leads",
                "description": "Search leads by name or email",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query (name or email)"}
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "delete_lead",
                "description": "Delete a lead from the CRM",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "lead_id": {"type": "string", "description": "ID of the lead to delete"}
                    },
                    "required": ["lead_id"]
                }
            },
            {
                "name": "list_leads_by_status",
                "description": "List all leads with a specific status",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "description": "Status to filter by (e.g., 'new', 'contacted', 'qualified', 'converted')"}
                    },
                    "required": ["status"]
                }
            },
            {
                "name": "get_lead_details",
                "description": "Get detailed information about a specific lead",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "lead_id": {"type": "string", "description": "ID of the lead"}
                    },
                    "required": ["lead_id"]
                }
            }
        ]

    def _load_crm_data(self):
        """Load CRM data from local file."""
        crm_path = Path("data/crm.json")
        if crm_path.exists():
            return json.loads(crm_path.read_text())
        return {"leads": []}

    def _execute_tool(self, tool_name: str, tool_input: dict):
        """Execute a tool and return result by delegating to `tools.crm_tools`."""
        # Add lead
        if tool_name == "add_lead":
            lead = add_lead(tool_input["name"], tool_input["email"])
            return f"✅ Added lead: {lead['name']} ({lead['id']})"

        # Update status
        if tool_name == "update_status":
            try:
                lead = update_status(tool_input["lead_id"], tool_input["status"])
                return f"✅ Updated {lead['name']} status to '{lead['status']}'"
            except Exception:
                return f"❌ Lead {tool_input['lead_id']} not found"

        # List leads
        if tool_name == "list_leads":
            crm = load_crm()
            if not crm.get("leads"):
                return "No leads in CRM"
            leads_str = "\n".join([f"  - {l['name']} ({l['id']}) - {l['email']} - Status: {l['status']}" for l in crm["leads"]])
            return f"📋 Leads:\n{leads_str}"

        # Add note
        if tool_name == "add_note":
            return add_note(tool_input["lead_id"], tool_input["note_text"])

        # Search
        if tool_name == "search_leads":
            results = search_leads(tool_input["query"])
            if not results:
                return f"❌ No leads found matching '{tool_input['query']}'"
            leads_str = "\n".join([f"  - {l['name']} ({l['id']}) - {l['email']}" for l in results])
            return f"🔍 Found {len(results)} lead(s):\n{leads_str}"

        # Delete
        if tool_name == "delete_lead":
            return delete_lead(tool_input["lead_id"])

        # List by status
        if tool_name == "list_leads_by_status":
            results = list_leads_by_status(tool_input["status"])
            if not results:
                return f"No leads with status '{tool_input['status']}'"
            leads_str = "\n".join([f"  - {l['name']} ({l['id']}) - {l['email']}" for l in results])
            return f"📋 {len(results)} lead(s) with status '{tool_input['status']}':\n{leads_str}"

        # Get details
        if tool_name == "get_lead_details":
            lead = get_lead_details(tool_input["lead_id"])
            if not lead:
                return f"❌ Lead {tool_input['lead_id']} not found"
            notes_str = "\n".join([f"    - {n.get('text', n)}" for n in lead.get("notes", [])])
            return (
                f"📊 Lead Details:\n  Name: {lead['name']}\n  Email: {lead['email']}\n  Status: {lead['status']}\n  Notes:\n{notes_str if notes_str else '    (no notes)'}"
            )

    def run(self, user_message: str) -> str:
        """Run agent with user instruction, handle tool calls."""
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        while True:
            # Get response from Claude
            response = self.client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=1024,
                tools=self.tools,
                messages=self.conversation_history
            )

            # Check if we're done (no more tool calls)
            if response.stop_reason == "end_turn":
                # Extract final text response
                final_response = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        final_response = block.text
                
                self.conversation_history.append({
                    "role": "assistant",
                    "content": response.content
                })
                return final_response

            # Handle tool use
            if response.stop_reason == "tool_use":
                self.conversation_history.append({
                    "role": "assistant",
                    "content": response.content
                })

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        tool_name = block.name
                        tool_input = block.input
                        
                        # Execute the tool
                        result = self._execute_tool(tool_name, tool_input)
                        print(f"🔧 Called {tool_name}: {result}")
                        
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result
                        })

                # Add tool results to conversation
                self.conversation_history.append({
                    "role": "user",
                    "content": tool_results
                })
            else:
                # Unexpected stop reason
                break

        return "Agent finished."

