#!/usr/bin/env python3
"""train_unsloth.py — Standalone Unsloth QLoRA Fine-Tuning Script for Bravo LLM.

Designed to be executed on an NVIDIA GPU instance (RunPod, Vast.ai, or local Linux GPU PC).
Fine-tunes Qwen 2.5 / DeepSeek models on custom ChatML datasets using Unsloth.

Requirements on GPU pod:
  pip install unsloth "xformers<0.0.27" "trl<0.9.0" peft acceleration datasets

Usage:
  python train_unsloth.py --dataset bravo_harness_sft.jsonl --model Qwen/Qwen2.5-14B-Instruct --output_dir ./models/bravo-qwen14b
"""

import argparse
import os
import sys

def main():
    parser = argparse.ArgumentParser(description="Unsloth QLoRA Trainer for Bravo LLM.")
    parser.add_argument("--dataset", type=str, default="bravo_harness_sft.jsonl", help="Path to ChatML JSONL dataset.")
    parser.add_argument("--model", type=str, default="unsloth/Qwen2.5-14B-Instruct-bnb-4bit", help="HuggingFace model ID or Unsloth quantized model.")
    parser.add_argument("--output_dir", type=str, default="./outputs", help="Directory to save output model.")
    parser.add_argument("--max_seq_length", type=int, default=4096, help="Maximum context sequence length.")
    parser.add_argument("--epochs", type=int, default=3, help="Number of training epochs.")
    parser.add_argument("--batch_size", type=int, default=2, help="Per-device train batch size.")
    parser.add_argument("--learning_rate", type=float, default=2e-4, help="Learning rate.")
    parser.add_argument("--export_gguf", action="store_true", help="Export to GGUF Q4_K_M after training.")
    args = parser.parse_args()

    print(f"[*] Initializing Unsloth QLoRA Fine-Tuning Pipeline...")
    print(f"    Model: {args.model}")
    print(f"    Dataset: {args.dataset}")
    print(f"    Output Dir: {args.output_dir}")

    try:
        from unsloth import FastLanguageModel
        from trl import SFTTrainer
        from transformers import TrainingArguments
        from datasets import load_dataset
    except ImportError:
        print("[!] Unsloth dependencies missing. Run:")
        print("    pip install unsloth trl peft accelerate datasets")
        print("[!] Note: Run this script on a Linux GPU instance (RunPod/Vast.ai) with NVIDIA CUDA.")
        sys.exit(1)

    # 1. Load model and tokenizer
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.model,
        max_seq_length=args.max_seq_length,
        load_in_4bit=True,
    )

    # 2. Add QLoRA adapters
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_alpha=16,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=3407,
    )

    # 3. Format ChatML dataset
    def formatting_prompts_func(examples):
        convs = examples["messages"]
        texts = []
        for conv in convs:
            formatted = ""
            for msg in conv:
                role = msg["role"]
                content = msg["content"]
                formatted += f"<|im_start|>{role}\n{content}<|im_end|>\n"
            texts.append(formatted)
        return {"text": texts}

    dataset = load_dataset("json", data_files={"train": args.dataset})
    dataset = dataset.map(formatting_prompts_func, batched=True)

    # 4. Configure Trainer
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset["train"],
        dataset_text_field="text",
        max_seq_length=args.max_seq_length,
        dataset_num_proc=2,
        packing=False,
        args=TrainingArguments(
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=4,
            warmup_steps=10,
            num_train_epochs=args.epochs,
            learning_rate=args.learning_rate,
            fp16=not FastLanguageModel.is_bfloat16_supported(),
            bf16=FastLanguageModel.is_bfloat16_supported(),
            logging_steps=1,
            optim="adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type="linear",
            seed=3407,
            output_dir=args.output_dir,
        ),
    )

    # 5. Train
    print("[*] Starting Unsloth training loop...")
    trainer_stats = trainer.train()
    print(f"[OK] Training complete. Loss: {trainer_stats.training_loss:.4f}")

    # 6. Save model adapters & GGUF
    print(f"[*] Saving fine-tuned model to {args.output_dir}...")
    model.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)

    if args.export_gguf:
        print("[*] Exporting model to GGUF (Q4_K_M) format for Ollama...")
        model.save_pretrained_gguf(args.output_dir, tokenizer, quantization_method="q4_k_m")
        print(f"[OK] GGUF saved in {args.output_dir}")

    print("[OK] Unsloth Fine-Tuning Pipeline Complete.")

if __name__ == "__main__":
    main()
