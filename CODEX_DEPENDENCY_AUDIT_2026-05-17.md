# CODEX DEPENDENCY AUDIT - 2026-05-17

## Yapilan Kurulum/Guncelleme

- WebView2 Runtime onarim/yeniden kurulum yapildi.
- Microsoft Visual C++ 2015+ x64 guncellendi: 14.51.36231.0.
- Microsoft Visual C++ 2015+ x86 guncellendi: 14.51.36231.0.
- Microsoft Visual C++ 2013 x64/x86 guncellendi: 12.0.40664.0.
- FFmpeg kuruldu: Gyan.FFmpeg 8.1.1 full build.
- Tesseract zaten kurulu bulundu: 5.4.0.20240606.
- FFmpeg ve Tesseract klasorleri kullanici PATH ortam degiskenine eklendi.
- D500_BASLAT.bat icine FFmpeg ve Tesseract PATH garantisi eklendi; YazKlinik yeni baslatmalarda bu araclari terminal PATH yenilenmese bile bulur.

## Dogrulama

- `ffmpeg -version`: 8.1.1-full_build-www.gyan.dev.
- `tesseract --version`: 5.4.0.20240606.
- WebView2 registry surumu: 148.0.3967.70.
- NVIDIA RTX 5090 surucu: 576.88, CUDA runtime: 12.9, GPU gorunuyor.

## NVIDIA Notu

- Resmi NVIDIA sayfasinda daha yeni Game Ready surumleri gorunuyor, ancak GPU surucu kurulumu ekran ve calisan servisleri kesebilir.
- Klinik server acikken otomatik NVIDIA driver upgrade zorlanmadi.
- NVIDIA guncellemesi yapilacaksa hasta/klinik is akisi kapaliyken, resmi NVIDIA App veya nvidia.com driver installer ile yapilmali.
