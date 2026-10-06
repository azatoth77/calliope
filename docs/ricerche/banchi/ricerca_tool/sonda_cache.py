"""Sonda: cosa riporta prompt_eval_count con la cache del prefisso, e dove finiscono i tool."""
import json, time, httpx
URL = "http://127.0.0.1:11434"
M = "gemma4:e4b-it-qat"
h = httpx.Client(base_url=URL, timeout=120)

def tool(n):
    return {"type": "function", "function": {"name": f"strumento_{n}", "description": f"Fa la cosa numero {n} in casa.",
            "parameters": {"type": "object", "properties": {"x": {"type": "string"}}, "required": []}}}

def chat(messages, tools):
    body = {"model": M, "messages": messages, "stream": False, "think": False, "tools": tools,
            "options": {"num_ctx": 16384, "temperature": 0.3, "num_predict": 1}, "keep_alive": "30m"}
    t = time.perf_counter(); r = h.post("/api/chat", json=body).json(); dt = time.perf_counter() - t
    return r.get("prompt_eval_count"), (r.get("prompt_eval_duration") or 0) / 1e6, round(dt * 1000)

storia = []
for i in range(12):
    storia += [{"role": "user", "content": f"Raccontami qualcosa di interessante sull'argomento numero {i}, per favore, con qualche dettaglio storico e geografico."},
               {"role": "assistant", "content": "Certo. " + "Questa è una risposta abbastanza lunga che parla di storia, geografia e curiosità varie. " * 6}]
sys_ = {"role": "system", "content": "Sei Calliope, un'assistente vocale. Rispondi in italiano."}
A = [tool(i) for i in range(10)]
B = [tool(i) for i in range(10, 20)]
q = {"role": "user", "content": "Che ore sono?"}
q2 = {"role": "user", "content": "E che giorno è?"}
print("freddo  A", chat([sys_] + storia + [q], A))
print("uguale  A", chat([sys_] + storia + [q], A))
print("dom.nuova A", chat([sys_] + storia + [q2], A))
print("tool B  ", chat([sys_] + storia + [q], B))
print("tool B ancora", chat([sys_] + storia + [q2], B))
print("senza tool", chat([sys_] + storia + [q], []))
print("sys diverso A", chat([{"role": "system", "content": "Sei Calliope. Rispondi."}] + storia + [q], A))
# sistema in coda: prefisso uguale, istruzione variabile dopo la storia
print("A + sys in coda 1", chat([sys_] + storia + [{"role": "system", "content": "Strumenti utili: luce."}, q], A))
print("A + sys in coda 2", chat([sys_] + storia + [{"role": "system", "content": "Strumenti utili: musica."}, q], A))
