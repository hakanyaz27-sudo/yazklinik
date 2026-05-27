# Axolotl — LLM Fine-Tune (yaz:latest'i kisisellestir)

Senin gecmis konsultasyon notlarini, raporlarini, alex_facts'leri kullanarak
**meditron:70b veya yaz:latest** modelini **kisisel sana ozel** versiyona donustur.

> NOT: Bu agir bir is (8-24 saat, RTX 5090 hep cizilir, 200 GB+ ara disk).
> Klinik 5-10 yil sonra "kendi modelin" ile cevap verir.

## Kurulum (gerektikce)

```powershell
# 1. Klasore git
cd D:\YazKlinik_Final_D500\akillilik\axolotl

# 2. Resmi repo
git clone https://github.com/axolotl-ai-cloud/axolotl.git .

# 3. Conda environment (axolotl Python 3.11 ister)
conda create -n axolotl python=3.11
conda activate axolotl

# 4. Bagimliliklar
pip3 install -e '.[flash-attn,deepspeed]'
pip3 install protobuf  # transformers icin

# 5. Hugging Face token (medical model'ler genelde gated)
huggingface-cli login

# 6. Egitim verisi hazirla (JSONL: question, answer)
python prepare_yazklinik_dataset.py  # senin scripti yaz; ornek altta
```

## Veri formati (ornek)

`yazklinik_qa.jsonl`:
```jsonl
{"instruction": "32 hafta gebe, TA 158/102, proteinuri +++. Ne yaparsin?", "output": "Preeklampsi sup; magnesium sulfate, hospitalizasyon..."}
{"instruction": "GDM hastasi 28 hafta, insulin baslayalim mi?", "output": "Diyet 2 hafta dene; HbA1c >6.5..."}
```

## Config (`yk-meditron-lora.yml`)

```yaml
base_model: epfl-llm/meditron-7b
adapter: lora
lora_r: 16
lora_alpha: 32
sequence_len: 4096
sample_packing: true
datasets:
  - path: ./yazklinik_qa.jsonl
    type: alpaca
num_epochs: 3
micro_batch_size: 4
gradient_accumulation_steps: 4
optimizer: adamw_torch
learning_rate: 2e-4
output_dir: ./yk-meditron-lora-out
```

## Egit

```powershell
accelerate launch -m axolotl.cli.train yk-meditron-lora.yml
# 6-18 saat RTX 5090 ile
```

## Ollama'ya alma

```powershell
# LoRA adapter'i merge edip GGUF'a cevir
python convert_to_gguf.py yk-meditron-lora-out
# Modelfile:
ollama create yk-meditron -f Modelfile
ollama run yk-meditron "preeklampsi"
```

## Sonra konsult ajanda kullan

`yazklinik_konsult_agent.py`:
```python
PREFERRED_MODELS_BY_STEP["ddx"] = ["yk-meditron", "meditron:70b", "qwen2.5:32b"]
```

## Etik / KVKK

- Egitim datasi anonim olmali (hasta adi YOK, sadece klinik mantik)
- Model ciktisi yine "doktor onayli oneri", direktif degil
- Hasta yazili rizasiz egitim data'ya hasta vakasi koyma
- TR mevzuat: "tibbi cihaz" siniflandirmasi sorgula

## Kaynak

- https://github.com/axolotl-ai-cloud/axolotl
- https://huggingface.co/docs/peft (LoRA)
- Meditron paper: arxiv 2311.16079
