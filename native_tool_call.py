import json
from urllib.request import urlopen

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from langchain_tools import calculate_mean


# Discover the actual model ID served by llama.cpp.
with urlopen("http://127.0.0.1:8080/v1/models", timeout=15) as response:
    model_name = json.load(response)["data"][0]["id"]


model = ChatOpenAI(
    model=model_name,
    base_url="http://127.0.0.1:8080/v1",
    api_key="local-only",
    temperature=0,
    max_tokens=256,
    timeout=180,
    max_retries=0,
    use_responses_api=False,
    extra_body={
        "chat_template_kwargs": {"enable_thinking": False},
    },
)

# Describe the available tool and require it for this experiment.
model_with_tools = model.bind_tools(
    [calculate_mean],
    tool_choice="calculate_mean",
    parallel_tool_calls=False,
)

reply = model_with_tools.invoke([
    HumanMessage(
        content=(
            "Use calculate_mean to find the average of "
            "the order_value_eur column."
        )
    )
])

print("MODEL TEXT:")
print(reply.content)

print("\nNATIVE TOOL REQUESTS:")
print(json.dumps(reply.tool_calls, indent=2))

if reply.response_metadata.get("finish_reason") == "length":
    raise ValueError("The model response was truncated.")

if reply.invalid_tool_calls:
    raise ValueError(f"Invalid tool calls: {reply.invalid_tool_calls}")

if len(reply.tool_calls) != 1:
    raise ValueError("Expected exactly one native tool call.")

call = reply.tool_calls[0]

if call["name"] != calculate_mean.name:
    raise ValueError("Unexpected tool name.")

# Python executes the request—not the model.
tool_result = calculate_mean.invoke(call)

print("\nRESULT MESSAGE TYPE:")
print(type(tool_result).__name__)

print("\nMATCHING TOOL CALL ID:")
print(tool_result.tool_call_id)

print("\nTOOL RESULT:")
print(tool_result.content)


from langchain_core.messages import SystemMessage


final_reply = model.invoke([
    SystemMessage(
        content=(
            "Answer briefly using only the tool result. "
            "Report the average order value, values used, "
            "and missing values excluded."
        )
    ),
    HumanMessage(
        content="What is the average recorded order value?"
    ),
    reply,
    tool_result,
])

if final_reply.response_metadata.get("finish_reason") == "length":
    raise ValueError("The final explanation was truncated.")

if not isinstance(final_reply.content, str) or not final_reply.content.strip():
    raise ValueError("The model returned no final explanation.")

print("\nFINAL ANSWER:")
print(final_reply.content)
