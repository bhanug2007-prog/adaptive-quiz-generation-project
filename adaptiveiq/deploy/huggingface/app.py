"""Upload this file as app.py in AdaptiveIQ's ZeroGPU Gradio Space."""
import json
import os

import gradio as gr
import spaces
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, token=False)
base_model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL, dtype=torch.bfloat16, low_cpu_mem_usage=True, token=False,
)
model = PeftModel.from_pretrained(
    base_model, os.environ["ADAPTER_REPO"], token=os.environ["HF_TOKEN"], torch_device="cpu",
).to("cuda").eval()


@spaces.GPU(duration=60)
@torch.inference_mode()
def generate(prompt: str) -> str:
    prompt = prompt.strip()
    if not prompt or len(prompt) > 24000:
        raise gr.Error("Enter a prompt of up to 24,000 characters.")

    if prompt.startswith('{"model":'):
        try:
            request = json.loads(prompt)
            messages = request["messages"]
            if not isinstance(messages, list) or not messages or any(
                not isinstance(message, dict)
                or message.get("role") not in ("system", "user", "assistant")
                or not isinstance(message.get("content"), str)
                for message in messages
            ):
                raise ValueError
            max_tokens = min(512, max(1, int(request["max_tokens"])))
            temperature = float(request["temperature"])
            top_p = float(request["top_p"])
            if not 0 <= temperature <= 2 or not 0 < top_p <= 1:
                raise ValueError
        except (ValueError, KeyError, TypeError, OverflowError) as error:
            raise gr.Error("Invalid AdaptiveIQ generation request.") from error
    else:
        messages = [
            {"role": "system", "content": "Generate one multiple-choice question with four distinct "
             "options, one correct answer letter, and a short explanation."},
            {"role": "user", "content": prompt},
        ]
        max_tokens, temperature, top_p = 256, 0.0, 1.0

    inputs = tokenizer.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True, return_dict=True, return_tensors="pt",
    ).to("cuda")
    input_length = inputs["input_ids"].shape[1]
    if input_length > 8192:
        raise gr.Error("The input exceeds 8,192 tokens.")
    sampling = {"temperature": temperature, "top_p": top_p} if temperature > 0 else {}
    output = model.generate(**inputs, max_new_tokens=max_tokens, do_sample=temperature > 0, **sampling)
    return tokenizer.decode(output[0, input_length:], skip_special_tokens=True).strip()


demo = gr.Interface(
    fn=generate,
    inputs=gr.Textbox(lines=3, label="Question prompt"),
    outputs=gr.Textbox(lines=10, label="Generated question"),
    title="AdaptiveIQ | Question Generation",
    api_name="generate",
)

if __name__ == "__main__":
    demo.queue().launch()
