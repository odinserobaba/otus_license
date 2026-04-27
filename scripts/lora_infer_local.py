#!/usr/bin/env python3
import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Local inference with base model + LoRA adapter (Transformers/PEFT)")
    parser.add_argument("--base-model", required=True, help="HF model id, e.g. Qwen/Qwen2.5-1.5B-Instruct")
    parser.add_argument("--adapter-path", required=True, help="Path to trained LoRA adapter")
    parser.add_argument("--question", required=True, help="User question")
    parser.add_argument("--max-new-tokens", type=int, default=420)
    args = parser.parse_args()

    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except Exception as e:  # noqa: BLE001
        print("Dependencies missing. Install in dedicated env:")
        print("pip install torch transformers peft accelerate")
        print(f"Import error: {e}")
        return

    dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    base = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        torch_dtype=dtype,
        device_map="auto",
    )
    model = PeftModel.from_pretrained(base, args.adapter_path)
    tok = AutoTokenizer.from_pretrained(args.base_model)

    prompt = (
        "Ты юридический ассистент по лицензированию ЕГАИС. "
        "Отвечай строго по вопросу, не выдумывай реквизиты.\n\n"
        f"Вопрос: {args.question}\n"
        "Ответ:"
    )
    inputs = tok(prompt, return_tensors="pt")
    if torch.cuda.is_available():
        inputs = {k: v.to(model.device) for k, v in inputs.items()}
    output_ids = model.generate(
        **inputs,
        max_new_tokens=args.max_new_tokens,
        do_sample=False,
        temperature=0.1,
    )
    text = tok.decode(output_ids[0], skip_special_tokens=True)
    print(text)


if __name__ == "__main__":
    main()
