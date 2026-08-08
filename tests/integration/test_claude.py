import os, pytest

# Live-API script — run directly: python tests/integration/test_claude.py
pytest.skip("Live Claude script — run directly, not via pytest", allow_module_level=True)

if __name__ == "__main__":
    os.environ["ANTHROPIC_API_KEY"] = open(".env").read().split("ANTHROPIC_API_KEY=")[1].split("\n")[0].strip()

    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=100,
        messages=[{"role": "user", "content": "გამარჯობა! ქართულად 1 წინადადება."}]
    )
    print("Claude:", resp.content[0].text)
    print("Tokens:", resp.usage.input_tokens, "in,", resp.usage.output_tokens, "out")
