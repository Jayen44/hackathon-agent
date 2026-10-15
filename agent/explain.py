"""LLM narration. The model only explains; it never computes the numbers."""
import os

from dotenv import load_dotenv

load_dotenv()


def explain(prev: dict | None, new: dict) -> str:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return f"Decision: {new['decision']} (score {new['score']:.2f}). [LLM disabled: no API key]"

    import anthropic

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-sonnet-5-5",
        max_tokens=300,
        messages=[
            {
                "role": "user",
                "content": (
                    "Explain this change to a non-expert in 2-3 sentences. "
                    "Use only the numbers given. Note uncertainty. Not financial advice.\n"
                    f"Previous: {prev}\nNew: {new}"
                ),
            }
        ],
    )
    return msg.content[0].text
