import json

from app.services.generation import get_generator

SYSTEM = "You answer only in JSON with a single key 'answer'."
USER = "In one sentence, what is a refund policy?"

for model in ("qwen2.5:3b", "gemma3:1b"):
    result = get_generator(model).generate(SYSTEM, USER)
    parsed = json.loads(result.text)
    print(f"{model}: {result.latency_ms} ms, in={result.input_tokens} out={result.output_tokens}")
    print(f"  answer: {parsed.get('answer')}")