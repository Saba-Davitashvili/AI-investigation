import os

from dotenv import load_dotenv
from groq import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    Groq,
    RateLimitError
)

from config import BASE_DIRECTORY


def main():
    load_dotenv(BASE_DIRECTORY / ".env")

    api_key = os.getenv("GROQ_API_KEY")

    if not api_key or api_key == "replace_with_your_key":
        print("Add your Groq API key to .env first.")
        return

    model = os.getenv(
        "GROQ_MODEL",
        "openai/gpt-oss-120b"
    )

    try:
        with Groq(
            api_key=api_key,
            timeout=30.0,
            max_retries=2
        ) as client:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Reply with one short sentence "
                            "confirming you received this message."
                        )
                    }
                ],
                max_completion_tokens=2048
            )

        message = response.choices[0].message.content

        if not message:
            print(
                "The API responded, but returned no visible text. "
                "We need to inspect the response settings."
            )
            return

        print(f"Model: {response.model}")
        print(f"Response: {message}")

        if response.usage:
            print(f"Total tokens: {response.usage.total_tokens}")

    except AuthenticationError:
        print("Authentication failed. Check your API key.")

    except RateLimitError:
        print("Rate limit reached. Wait before trying again.")

    except APIConnectionError:
        print("Could not connect to Groq. Check your connection.")

    except APIStatusError as error:
        print(f"Provider returned HTTP {error.status_code}.")


if __name__ == "__main__":
    main()