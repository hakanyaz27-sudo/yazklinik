# MedSAM — Tibbi Goruntu Segmentasyon (USG/MR fetal organ konturu)

Bilim adamlarinin "Segment Anything Model"in tibbi adaptasyonu.
USG'de **fetal beyin / kalp / placenta / uzun kemik** otomatik konturu.

## Kurulum (opsiyonel, RTX 5090 ile harika)

```powershell
# 1. Repo
cd D:\YazKlinik_Final_D300\akillilik\medsam
git clone https://github.com/bowang-lab/MedSAM.git .

# 2. Python paketler (ana .venv'e)
& D:\YazKlinik_Final_D300\.venv\Scripts\pip.exe install -e .
& D:\YazKlinik_Final_D300\.venv\Scripts\pip.exe install torch torchvision opencv-python segment-anything

# 3. Model agirliklari (~700 MB)
mkdir work_dir\MedSAM
curl -L -o work_dir\MedSAM\medsam_vit_b.pth `
    https://huggingface.co/wanglab/medsam/resolve/main/medsam_vit_b.pth

# 4. Test (script icinde demo notebook var)
& D:\YazKlinik_Final_D300\.venv\Scripts\python.exe scripts\app.py
# Gradio acilir: http://127.0.0.1:7860
```

## YazKlinik wire (gelecek)

Konsultasyon ajaninda USG resmi yuklenebilir, MedSAM kontur cizebilir:

```python
# yazklinik_usg_rapor_agent.py'a yeni:
def auto_segment_organs(usg_image_path):
    from segment_anything import SamPredictor
    from medsam_inference import medsam_predictor
    img = cv2.imread(usg_image_path)
    masks = medsam_predictor(img)
    return masks  # head, abdomen, femur cikti
```

## Bilim notu

- Paper: Ma & Wang, Nature Comm. 2024
- Ucretsiz, MIT license
- ~700 MB, GPU 4 GB VRAM kafi (RTX 5090 fazlasiyla)
- Limit: Voluson USG'de fetal yuz tanima %85+ accuracy
