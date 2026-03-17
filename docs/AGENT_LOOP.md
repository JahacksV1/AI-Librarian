# AIJAH Agent Loop

> The agent loop is the brainstem of the system.
> Everything else — tools, memory, the database, the UI — is peripheral to it.
> If the agent loop is wrong, everything is wrong.

---

## What the Agent Loop Is

The agent loop is the code that runs every time the user sends a message and expects the AI to do something. It is an iterative cycle:

```
1. Assemble context from DB + memory
2. Call the model (Ollama) with that context + available tools
3. Model either responds with text, or requests a tool call
4. If tool call → execute the MCP tool → append result → go back to step 2
5. If text response → stream it to the UI → write to DB → loop ends
```

This is not a one-shot call. It is a loop. The model can call tools multiple times in a single user message — for example: scan folder, then propose a plan, then update task state — all before producing its final text response.

---

## The Loop in Pseudocode

```python
async def run_agent_loop(session_id: str, user_message: str):
    # 1. Persist the user message
    await db.insert_message(session_id, role=SYSTEM, content=user_message)

    # 2. Assemble context packet
    context = await assemble_context(session_id)

    # 3. Discover available MCP tools (done once at startup, cached)
    tools = mcp_client.list_tools()  # converted to Ollama function-call format

    # 4. Main loop
    while True:
        # Call Ollama with full context + tool schemas
        response = await ollama.chat(
            model=OLLAMA_MODEL,
            messages=context.to_message_list(),
            tools=tools,
            stream=True
        )

        # Stream tokens to frontend via SSE
        full_response = await stream_to_sse(response, session_id)

        # Did the model request a tool call?
        if full_response.tool_calls:
            for tool_call in full_response.tool_calls:
                # Log the tool call
                await log_event("tool_call", tool=tool_call.name, args=tool_call.args)

                # Execute via MCP
                result = await mcp_client.call_tool(
                    tool_call.name,
                    tool_call.args
                )

                # Append tool result to context
                context.append_tool_result(
                    tool_name=tool_call.name,
                    tool_call_id=tool_call.id,
                    result=result
                )

                # Persist as a TOOL message
                await db.insert_message(
                    session_id,
                    role=TOOL,
                    content=result,
                    tool_name=tool_call.name,
                    tool_call_id=tool_call.id
                )

            # Continue the loop — model will see tool results
            continue

        # No tool calls — model produced a final text response
        await db.insert_message(session_id, role=ASSISTANT, content=full_response.content)
        break  # loop ends
```

Key points:
- The loop continues as long as the model is requesting tool calls
- Each tool result is appended to the running message list before the next model call
- Tokens stream to the frontend in real time via SSE during each model call
- Every message (user, assistant, tool) is persisted to `session_messages`

---

## Context Assembly

The context packet is what the model sees. The quality of context determines the quality of the response. A model with bad context feels stupid. A model with good context feels powerful. Context is where the intelligence lives.

### Phase 1 context packet (what gets assembled before every Ollama call)

```python
async def assemble_context(session_id: str) -> ContextPacket:
    return ContextPacket(
        # 1. System prompt — defines AIJAH's role and safety rules
        system_prompt=load_system_prompt(),

        # 2. Active policies — safety rules, naming conventions
        policies=await db.get_active_policies(user_id),

        # 3. User preferences — known naming habits, folder structure preferences
        preferences=await db.get_user_preferences(user_id),

        # 4. Task state — what we're currently trying to do
        task_state=await db.get_task_state(session_id),

        # 5. Session messages — full conversation so far
        messages=await db.get_session_messages(session_id),
    )
```

### Phase 2 context packet additions (not in Phase 1)

```python
        # 6. Similar past memory events — vector-retrieved by similarity to current goal
        similar_events=await memory.retrieve_similar(current_goal, top_k=5),

        # 7. Relevant file entities — files the model mentioned or scanned recently
        relevant_files=await db.get_recently_mentioned_files(session_id),
```

### System prompt (Phase 1)

The system prompt is the non-negotiable first message in every context. It tells the model:

```
You are AIJAH, a local file assistant. Your job is to help the user organize their files safely.

Rules you must always follow:
- Never perform file operations without a plan being proposed and approved first.
- Always call propose_plan before suggest any rename, move, or archive action.
- Never delete files. Use archive instead.
- Only operate within the sandbox root path.
- If you are unsure about a file's purpose, ask the user before including it in a plan.
- When you propose a plan, explain your reasoning clearly so the user can make an informed decision.
```

---

## The MCP Tool Call Cycle

MCP is a JSON-RPC 2.0 protocol. The agent loop connects to the MCP server at startup and holds a persistent session.

```
Startup (once):
  Agent loop → MCP server: initialize { protocolVersion, capabilities }
  MCP server → Agent loop: initialize result { capabilities }
  Agent loop → MCP server: initialized (notification)
  Agent loop → MCP server: tools/list
  MCP server → Agent loop: list of tool schemas
  Agent loop: convert schemas to Ollama function-call format, cache

Per tool call (many times per loop iteration):
  Model output: { tool_name: "scan_folder", args: { path: "/sandbox/invoices" } }
  Agent loop → MCP server: tools/call { name: "scan_folder", arguments: { path: ... } }
  MCP server: runs the function, writes to DB
  MCP server → Agent loop: { content: [{ type: "text", text: "{ files: [...] }" }] }
  Agent loop: appends result to context, continues loop
```

The model never talks to the MCP server directly. The agent loop is the bridge:
- Model → agent loop: tool call request (just JSON in the response)
- Agent loop → MCP server: actual RPC call
- MCP server → agent loop: result
- Agent loop → model: result appended to message history

---

## Observability: What You Must Log

Agent systems fail silently. A model makes a wrong decision and you have no idea why — because you can't see what context it was given. Observability is not optional.

For every agent loop run, log:

### 1. Context snapshot (before each Ollama call)
```python
log.info("agent_loop.context", extra={
    "session_id": session_id,
    "message_count": len(context.messages),
    "has_task_state": context.task_state is not None,
    "active_plan_id": context.task_state.active_plan_id,
    "current_step": context.task_state.current_step,
    "token_estimate": estimate_tokens(context),
})
```

### 2. Model response (after each Ollama call)
```python
log.info("agent_loop.model_response", extra={
    "session_id": session_id,
    "had_tool_calls": bool(response.tool_calls),
    "tool_names": [tc.name for tc in response.tool_calls],
    "response_length": len(response.content),
})
```

### 3. Tool call + result
```python
log.info("agent_loop.tool_call", extra={
    "session_id": session_id,
    "tool": tool_call.name,
    "args": tool_call.args,
})
log.info("agent_loop.tool_result", extra={
    "session_id": session_id,
    "tool": tool_call.name,
    "result_preview": str(result)[:200],
    "success": "error" not in result,
})
```

### 4. State transitions
```python
log.info("agent_loop.state_transition", extra={
    "session_id": session_id,
    "from_step": old_step,
    "to_step": new_step,
    "trigger": "tool_result" or "user_input",
})
```

### Why this matters

When something goes wrong (model proposes a bad rename, plan doesn't appear, execution fails), you open the logs and see:

- What context the model received
- What tool it called and with what arguments
- What the tool returned
- What the model decided next

Without these logs, debugging an agent loop is guesswork.

---

## The Five Things That Control Agent Quality

In order of impact:

### 1. Context quality (most important)
The model is only as good as what you put in the context. Bad context = dumb behavior. Good context (task state, policies, recent messages, preferences) = smart behavior. This matters more than which model you use.

### 2. Tool contracts (second most important)
If tool schemas are vague, the model will call them with wrong arguments. If tool names are ambiguous, the model will call the wrong tool. Tool names and descriptions must be clear and unambiguous. This is the `propose_plan` tool's description:
```
"Generate a file reorganization plan and write it to the database. 
Call this tool when you have scanned a folder and are ready to suggest 
how to rename and move files. Do NOT call execute_action before this."
```

### 3. System prompt precision
Vague system prompts produce vague behavior. The system prompt must state the rules clearly and absolutely. Include what the model must always do, what it must never do, and what it should ask the user when unsure.

### 4. Model selection
For Phase 1, `qwen2.5` is the best local option for tool-calling. Accept that it will feel less capable than Claude or GPT-4 in Phase 1. That is expected. The architecture is right; the model will improve as you upgrade Ollama or switch models.

### 5. Loop termination
The loop must have a maximum iteration count. If the model keeps calling tools without producing a final response, the loop must stop. A reasonable limit is 10 tool calls per user message. Beyond that, log the error and return a fallback response.

```python
MAX_TOOL_ITERATIONS = 10
iteration = 0

while True:
    iteration += 1
    if iteration > MAX_TOOL_ITERATIONS:
        log.error("agent_loop.max_iterations_exceeded", session_id=session_id)
        await db.insert_message(session_id, role=ASSISTANT,
            content="I ran into an issue completing that task. Please try again.")
        break
    ...
```

---

## How the Agent Loop Connects to the Rest of the System

```
User sends message
        │
        ▼
  POST /sessions/{id}/messages
        │
        ▼
  agent.run_agent_loop()
        │
        ├── assembles context from DB
        │       └── reads: sessions, session_messages, task_state,
        │                  user_preferences, operational_policies
        │
        ├── calls Ollama (streams tokens → SSE → browser)
        │
        ├── if tool call:
        │       └── mcp_client.call_tool()
        │               └── mcp_server.py runs the Python function
        │                       ├── scan_folder: reads filesystem, writes file_entities
        │                       ├── propose_plan: writes plans + plan_actions
        │                       ├── execute_action: reads file_entities, moves files,
        │                       │                   writes memory_events
        │                       ├── get/update_task_state: reads/writes task_state
        │                       └── read_file_metadata: reads file_entities
        │
        └── final response: writes to session_messages, SSE message_complete event
```

---

## Phase 2 Loop Enhancements (do not implement in Phase 1)

In Phase 2, the context assembler gains vector retrieval:

```python
# Phase 2 addition — not in Phase 1
similar_events = await vector_db.search(
    embedding=embed(current_goal),
    table="memory_event_embeddings",
    top_k=5
)
```

And new MCP tools are added:
- `read_document` — extract text from PDF, Word, image
- `search_memory` — semantic search across past memory events
- `classify_file` — link a file to a known entity

The loop structure itself does not change. Only the context gets richer and the tool list grows.
