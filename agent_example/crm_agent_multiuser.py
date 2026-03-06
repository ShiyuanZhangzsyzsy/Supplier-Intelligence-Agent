"""Multi-user CRM Agent."""
import json
import os
from datetime import datetime
from anthropic import Anthropic
from sqlalchemy import func
from database import SessionLocal, Lead, Task

class CRMAgent:
    def __init__(self, user_id: int):
        """Initialize agent for a specific user."""
        self.user_id = user_id
        api_key = os.getenv("ANTHROPIC_API_KEY")
        # If API key missing, continue but disable remote LLM calls; we'll use local heuristics as fallback.
        if not api_key:
            self.client = None
        else:
            self.client = Anthropic()
        self.conversation_history = []
        self.db = SessionLocal()
        
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
                "description": "Update a lead's status by lead ID or lead name",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "lead_id": {"type": "string", "description": "ID of the lead (optional if lead_name is provided)"},
                        "lead_name": {"type": "string", "description": "Name of the lead (optional if lead_id is provided)"},
                        "status": {"type": "string", "description": "New status (e.g., 'new', 'contacted', 'qualified', 'converted')"}
                    },
                    "required": ["status"]
                }
            },
            {
                "name": "update_email",
                "description": "Update a lead's email address by lead ID or lead name",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "lead_id": {"type": "string", "description": "ID of the lead (optional if lead_name is provided)"},
                        "lead_name": {"type": "string", "description": "Name of the lead (optional if lead_id is provided)"},
                        "email": {"type": "string", "description": "New email address"}
                    },
                    "required": ["email"]
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
            },
            {
                "name": "create_task",
                "description": "Create a follow-up task for the current user",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Task title"},
                        "lead_id": {"type": "string", "description": "Optional lead ID"},
                        "priority": {"type": "string", "description": "low, medium, or high"},
                        "due_at": {"type": "string", "description": "Optional due datetime in ISO format"}
                    },
                    "required": ["title"]
                }
            },
            {
                "name": "list_tasks",
                "description": "List tasks for the current user",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "description": "Optional status filter: open or completed"}
                    }
                }
            },
            {
                "name": "complete_task",
                "description": "Mark a task as completed by task ID",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "Task ID to complete"}
                    },
                    "required": ["task_id"]
                }
            }
        ]

    def _execute_tool(self, tool_name: str, tool_input: dict):
        """Execute a tool and return result."""
        def _parse_lead_id(raw_lead_id):
            value = str(raw_lead_id).strip()
            if value.isdigit():
                return int(value)
            if value.lower().startswith("lead_"):
                suffix = value.split("_", 1)[1]
                if suffix.isdigit():
                    return int(suffix)
            return None

        def _safe_notes(raw_notes):
            if not raw_notes:
                return []
            try:
                parsed = json.loads(raw_notes)
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return []

        def _parse_iso_datetime(value):
            if value in (None, ""):
                return None, None
            if not isinstance(value, str):
                return None, "❌ due_at must be an ISO-8601 datetime string"
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")), None
            except ValueError:
                return None, "❌ Invalid due_at format. Use ISO-8601, e.g. 2026-02-23T10:00:00Z"

        def _resolve_user_lead(tool_payload: dict):
            if tool_payload.get("lead_id") is not None:
                lead_id = _parse_lead_id(tool_payload.get("lead_id"))
                if lead_id is None:
                    return None, f"❌ Invalid lead ID '{tool_payload.get('lead_id')}'"
                lead = self.db.query(Lead).filter(Lead.id == lead_id, Lead.user_id == self.user_id).first()
                if not lead:
                    return None, f"❌ Lead {tool_payload.get('lead_id')} not found"
                return lead, None

            lead_name = str(tool_payload.get("lead_name", "")).strip()
            if not lead_name:
                return None, "❌ Please provide either lead_id or lead_name"

            exact_matches = self.db.query(Lead).filter(
                Lead.user_id == self.user_id,
                Lead.name.ilike(lead_name)
            ).all()
            if len(exact_matches) == 1:
                return exact_matches[0], None
            if len(exact_matches) > 1:
                ids = ", ".join([str(lead.id) for lead in exact_matches])
                return None, f"❌ Multiple leads named '{lead_name}' found. Use lead_id: {ids}"

            partial_matches = self.db.query(Lead).filter(
                Lead.user_id == self.user_id,
                Lead.name.ilike(f"%{lead_name}%")
            ).all()
            if len(partial_matches) == 1:
                return partial_matches[0], None
            if len(partial_matches) > 1:
                ids = ", ".join([f"{lead.name} ({lead.id})" for lead in partial_matches[:10]])
                return None, f"❌ Multiple matching leads for '{lead_name}': {ids}. Please use lead_id."

            return None, f"❌ Lead '{lead_name}' not found"

        if tool_name == "add_lead":
            candidate_email = str(tool_input["email"]).strip()
            normalized_email = candidate_email.lower()
            duplicate_lead = self.db.query(Lead).filter(
                Lead.user_id == self.user_id,
                func.lower(Lead.email) == normalized_email
            ).first()
            if duplicate_lead:
                return (
                    f"❌ A lead with email '{candidate_email}' already exists: "
                    f"{duplicate_lead.name} ({duplicate_lead.id}). "
                    "Try updating that lead instead of creating a new one."
                )

            lead = Lead(
                user_id=self.user_id,
                name=tool_input["name"],
                email=candidate_email,
                status="new",
                notes=json.dumps([])
            )
            self.db.add(lead)
            self.db.commit()
            self.db.refresh(lead)
            return f"✅ Added lead: {lead.name} ({lead.id})"

        if tool_name == "update_status":
            lead, resolve_error = _resolve_user_lead(tool_input)
            if resolve_error:
                return resolve_error
            lead.status = tool_input["status"]
            self.db.commit()
            self.db.refresh(lead)
            return f"✅ Updated {lead.name} status to '{lead.status}'"

        if tool_name == "update_email":
            lead, resolve_error = _resolve_user_lead(tool_input)
            if resolve_error:
                return resolve_error
            lead.email = str(tool_input["email"]).strip()
            self.db.commit()
            self.db.refresh(lead)
            return f"✅ Updated {lead.name} email to '{lead.email}'"

        if tool_name == "list_leads":
            leads = self.db.query(Lead).filter(Lead.user_id == self.user_id).all()
            if not leads:
                return "No leads in CRM"
            leads_str = "\n".join([f"  - {lead.name} ({lead.id}) - {lead.email} - Status: {lead.status}" for lead in leads])
            return f"📋 Leads:\n{leads_str}"

        if tool_name == "add_note":
            lead, resolve_error = _resolve_user_lead(tool_input)
            if resolve_error:
                return resolve_error
            notes = _safe_notes(lead.notes)
            notes.append({"text": tool_input["note_text"]})
            lead.notes = json.dumps(notes)
            self.db.commit()
            self.db.refresh(lead)
            return f"✅ Added note to {lead.name}"

        if tool_name == "search_leads":
            query = str(tool_input["query"]).strip().lower()
            leads = self.db.query(Lead).filter(Lead.user_id == self.user_id).all()
            results = [
                lead for lead in leads
                if query in (lead.name or "").lower() or query in (lead.email or "").lower()
            ]
            if not results:
                return f"❌ No leads found matching '{tool_input['query']}'"
            leads_str = "\n".join([f"  - {lead.name} ({lead.id}) - {lead.email}" for lead in results])
            return f"🔍 Found {len(results)} lead(s):\n{leads_str}"

        if tool_name == "delete_lead":
            lead, resolve_error = _resolve_user_lead(tool_input)
            if resolve_error:
                return resolve_error
            lead_id = lead.id
            self.db.delete(lead)
            self.db.commit()
            return f"✅ Deleted lead {lead_id}"

        if tool_name == "list_leads_by_status":
            status = str(tool_input["status"]).strip().lower()
            leads = self.db.query(Lead).filter(Lead.user_id == self.user_id).all()
            results = [lead for lead in leads if (lead.status or "").lower() == status]
            if not results:
                return f"No leads with status '{tool_input['status']}'"
            leads_str = "\n".join([f"  - {lead.name} ({lead.id}) - {lead.email}" for lead in results])
            return f"📋 {len(results)} lead(s) with status '{tool_input['status']}':\n{leads_str}"

        if tool_name == "get_lead_details":
            lead, resolve_error = _resolve_user_lead(tool_input)
            if resolve_error:
                return resolve_error
            notes = _safe_notes(lead.notes)
            notes_str = "\n".join([f"    - {n.get('text', n)}" for n in notes])
            return (
                f"📊 Lead Details:\n  Name: {lead.name}\n  Email: {lead.email}\n  Status: {lead.status}\n  Notes:\n{notes_str if notes_str else '    (no notes)'}"
            )

        if tool_name == "create_task":
            title = str(tool_input.get("title", "")).strip()
            if not title:
                return "❌ Task title is required"

            priority = str(tool_input.get("priority", "medium")).strip().lower() or "medium"
            if priority not in {"low", "medium", "high"}:
                return "❌ Priority must be one of: low, medium, high"

            due_at, due_error = _parse_iso_datetime(tool_input.get("due_at"))
            if due_error:
                return due_error

            lead_id = tool_input.get("lead_id")
            lead_ref = None
            if lead_id is not None:
                parsed_lead_id = _parse_lead_id(lead_id)
                if parsed_lead_id is None:
                    return f"❌ Invalid lead ID '{lead_id}'"
                lead_ref = self.db.query(Lead).filter(
                    Lead.id == parsed_lead_id,
                    Lead.user_id == self.user_id
                ).first()
                if not lead_ref:
                    return f"❌ Lead {lead_id} not found"

            task = Task(
                user_id=self.user_id,
                lead_id=lead_ref.id if lead_ref else None,
                title=title,
                due_at=due_at,
                priority=priority,
                status="open"
            )
            self.db.add(task)
            self.db.commit()
            self.db.refresh(task)
            next_step = "You can ask me to list tasks or complete this task later."
            due_text = f", due {task.due_at.isoformat()}" if task.due_at else ""
            lead_text = f", linked to lead {task.lead_id}" if task.lead_id else ""
            return f"✅ Created task {task.id}: {task.title} [{task.priority}]{due_text}{lead_text}. {next_step}"

        if tool_name == "list_tasks":
            status_filter = str(tool_input.get("status", "")).strip().lower()
            tasks_query = self.db.query(Task).filter(Task.user_id == self.user_id)
            if status_filter:
                if status_filter not in {"open", "completed"}:
                    return "❌ Status filter must be 'open' or 'completed'"
                tasks_query = tasks_query.filter(Task.status == status_filter)
            tasks = tasks_query.order_by(Task.due_at.is_(None), Task.due_at.asc(), Task.created_at.desc()).all()
            if not tasks:
                if status_filter:
                    return f"No {status_filter} tasks found. You can ask me to create one."
                return "No tasks yet. You can ask me to create a follow-up task."
            tasks_str = "\n".join([
                f"  - Task {task.id}: {task.title} | {task.status} | {task.priority}"
                f"{f' | due {task.due_at.isoformat()}' if task.due_at else ''}"
                f"{f' | lead {task.lead_id}' if task.lead_id else ''}"
                for task in tasks
            ])
            return f"🗂️ Tasks:\n{tasks_str}\nNext step: ask me to complete a task by ID."

        if tool_name == "complete_task":
            task_id_raw = tool_input.get("task_id")
            parsed_task_id = _parse_lead_id(task_id_raw)
            if parsed_task_id is None:
                return f"❌ Invalid task ID '{task_id_raw}'"
            task = self.db.query(Task).filter(Task.id == parsed_task_id, Task.user_id == self.user_id).first()
            if not task:
                return f"❌ Task {task_id_raw} not found"
            task.status = "completed"
            self.db.commit()
            self.db.refresh(task)
            return f"✅ Completed task {task.id}: {task.title}. Next step: ask me for open tasks."

        return f"❌ Unknown tool: {tool_name}"

    def run(self, user_message: str) -> str:
        """Run agent with user instruction, handle tool calls."""
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        # If no LLM client available, use a local heuristic fallback
        if not self.client:
            fallback = self._heuristic_execute(user_message)
            self.db.close()
            return fallback

        # Otherwise try calling the remote LLM, but catch errors and fallback to a local parser
        try:
            while True:
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
                    self.db.close()
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

        except Exception as e:
            # Log and fallback to a safe local heuristic for simple instructions
            print("LLM call failed, falling back to local heuristic:", e)
            fallback = self._heuristic_execute(user_message)
            self.db.close()
            return fallback

        self.db.close()
        return "Agent finished."

    def _heuristic_execute(self, message: str) -> str:
        """A simple, deterministic parser for common CRM instructions.

        Currently supports patterns like:
        - Add a lead named <Name> with email <email>
        - Add lead <Name> <email>
        - Update <Name> status to <status>
        - Update <Name> email to <email>
        """
        import re

        normalized_message = (message or "").strip()

        status_update_patterns = [
            r"update\s+(?:lead\s+)?(?:named\s+)?([\w\s'\-]+?)\s+status\s+to\s+(new|contacted|qualified|converted)",
            r"change\s+(?:the\s+)?status\s+of\s+([\w\s'\-]+?)\s+to\s+(new|contacted|qualified|converted)",
        ]
        for pattern in status_update_patterns:
            status_match = re.search(pattern, normalized_message, re.IGNORECASE)
            if status_match:
                lead_name = status_match.group(1).strip()
                status_value = status_match.group(2).strip().lower()
                return self._execute_tool("update_status", {"lead_name": lead_name, "status": status_value})

        email_update_patterns = [
            r"update\s+(?:lead\s+)?(?:named\s+)?([\w\s'\-]+?)\s+email\s+to\s+([\w\.-]+@[\w\.-]+)",
            r"change\s+(?:the\s+)?email\s+of\s+([\w\s'\-]+?)\s+to\s+([\w\.-]+@[\w\.-]+)",
        ]
        for pattern in email_update_patterns:
            email_change_match = re.search(pattern, normalized_message, re.IGNORECASE)
            if email_change_match:
                lead_name = email_change_match.group(1).strip()
                updated_email = email_change_match.group(2).strip()
                return self._execute_tool("update_email", {"lead_name": lead_name, "email": updated_email})

        create_task_patterns = [
            r"(?:create|add)\s+(?:a\s+)?task\s+(?:to\s+)?(.+)",
            r"remind\s+me\s+to\s+(.+)",
        ]
        for pattern in create_task_patterns:
            create_task_match = re.search(pattern, normalized_message, re.IGNORECASE)
            if create_task_match:
                task_title = create_task_match.group(1).strip().rstrip(".")
                if task_title:
                    return self._execute_tool("create_task", {"title": task_title})

        list_tasks_match = re.search(r"(?:list|show)(?:\s+me)?\s+(open\s+|completed\s+)?tasks", normalized_message, re.IGNORECASE)
        if list_tasks_match:
            status_token = (list_tasks_match.group(1) or "").strip().lower()
            status_value = status_token if status_token in {"open", "completed"} else ""
            payload = {"status": status_value} if status_value else {}
            return self._execute_tool("list_tasks", payload)

        complete_task_match = re.search(r"(?:complete|finish|done)\s+(?:task\s*)?(\d+)", normalized_message, re.IGNORECASE)
        if complete_task_match:
            return self._execute_tool("complete_task", {"task_id": complete_task_match.group(1)})

        # Try to find an email
        email_match = re.search(r"[\w\.-]+@[\w\.-]+", normalized_message)
        name_match = None

        # Common phrasing: "Add a lead named NAME with email EMAIL"
        m = re.search(r"add (?:a )?lead(?: named)?\s+([\w\s'-]+?)\s+(?:with )?email", normalized_message, re.IGNORECASE)
        if m:
            name_match = m.group(1).strip()
        else:
            # Fallback: "Add lead NAME EMAIL" -> take the token(s) before email
            if email_match:
                before = normalized_message[: email_match.start()].strip()
                parts = before.split()
                # assume last two tokens might be the name, but keep it simple: take last 3 tokens
                name_match = " ".join(parts[-3:]).strip() if parts else None

        if name_match and email_match:
            name = name_match
            email = email_match.group(0)
            result = self._execute_tool("add_lead", {"name": name, "email": email})
            return result

        return "Could not interpret instruction locally. LLM needed."
