#This function sends messages to llama-server and extracts the final answer. It also rejects truncated or empty responses—receiving a response does not automatically mean the model completed its task.

#Expected behavior: the model should acknowledge that it needs the data. It should not invent an average.

import json
from urllib.request import Request, urlopen


URL = "http://127.0.0.1:8080/v1/chat/completions"


def chat(messages):
    payload = {
        "messages": messages,
        "temperature": 0,
        "max_tokens": 256,
        "stream": False,
        "chat_template_kwargs": {
            "enable_thinking": False,
        },
    }

    request = Request(
        URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    with urlopen(request, timeout=180) as response:
        result = json.load(response)

    choice = result["choices"][0]
    content = choice["message"].get("content") or ""

    if choice.get("finish_reason") != "stop":
        raise ValueError(
            f"Incomplete response: {choice.get('finish_reason')}"
        )

    if not content.strip():
        raise ValueError("The model returned no final answer.")

    return content


if __name__ == "__main__":
    answer = chat([
        {
            "role": "system",
            "content": "Answer briefly and do not invent unavailable data.",
        },
        {
            "role": "user",
            "content": (
                "What is the average thickness in my dataset? "
                "I have not provided the dataset."
            ),
        },
    ])

    print(answer)
