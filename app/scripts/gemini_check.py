import json

from app.services.generation import get_generator

SYSTEM = "You answer only in JSON with a single key 'answer'."
USER = "In one sentence, what is a refund policy?"
SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}

for model in ("gemini:gemini-3.5-flash-lite", "gemini:gemini-3.8-flash", "gemini:gemma-4-31b-it"):
    try:
        r = get_generator(model).generate(SYSTEM, USER, SCHEMA)
        print(f"{model}: {r.latency_ms} ms, in={r.input_tokens} out={r.output_tokens}")
        print(f"  answer: {json.loads(r.text).get('answer')}")
    except Exception as e:
        print(f"{model}: FAILED {type(e).__name__}: {str(e)[:300]}")