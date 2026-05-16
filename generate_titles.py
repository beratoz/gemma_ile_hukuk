# =============================================================
# TEK SEFERLİK: TCK madde başlıklarını LM Studio ile üret
# tck_maddeler_temiz.json -> her madde için 1-3 kelimelik başlık
# Çıktı: ceza_kanunu_duzeltilmis/tck_basliklar.json
#
# Önkoşul: LM Studio çalışıyor olmalı (1234 portunda)
# Çalışma süresi: ~20-30 dakika (343 madde × ~3-5 sn)
# Yeniden başlatılabilir: mevcut çıktı dosyası varsa kaldığı yerden devam eder
# =============================================================

import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# --- 1. AYARLAR ---
load_dotenv()

JSON_PATH = "C:/Users/berat/Desktop/Gemma_Hukuk/ceza_kanunu_duzeltilmis/tck_maddeler_temiz.json"
OUTPUT_PATH = "C:/Users/berat/Desktop/Gemma_Hukuk/ceza_kanunu_duzeltilmis/tck_basliklar.json"

LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234/v1")
LM_STUDIO_API_KEY = os.getenv("LM_STUDIO_API_KEY", "lm-studio")
LM_MODEL_NAME = os.getenv("LM_MODEL_NAME", "google/gemma-4-e4b")

# İçeriğin yalnızca ilk N karakteri prompta gönderilir (uzun maddelerde token tasarrufu)
ICERIK_KISALTMA = 600

# --- 2. PROMPT ---
TITLE_PROMPT = """Sen bir Türk Ceza Kanunu uzmanısın. Sana verilen TCK madde metnini okuyup, bu maddenin resmi marjinal başlığını çıkar.

KURALLAR:
- Sadece 1-5 kelimelik kısa başlığı yaz, başka HİÇBİR ŞEY yazma.
- Türk hukuk literatüründe yaygın kullanılan terminolojiyi tercih et.
- Örnek başlıklar: "Hakaret", "Hırsızlık", "Kasten Öldürme", "Cinsel Saldırı", "Mala Zarar Verme", "Görevi Kötüye Kullanma"
- "Madde X" ya da "TCK Madde X" yazma, sadece kavramsal başlık.
- Açıklama, tire, parantez, numara YAZMA.
- Hiçbir cümle kurma. Sadece başlık ifadesi.
- Eğer madde bir tanım/genel hüküm ise (örn. "Bu kanunun amacı..."), kısaca konusu ne ise onu yaz (örn. "Kanunun Amacı", "Tanımlar")."""


def title_for(client: OpenAI, madde_no: int, icerik: str) -> str:
    """Tek bir madde için başlık üret."""
    snippet = icerik[:ICERIK_KISALTMA]
    user_msg = f"TCK Madde {madde_no} metni:\n\n{snippet}\n\nBaşlık:"

    cevap = client.chat.completions.create(
        model=LM_MODEL_NAME,
        messages=[
            {"role": "system", "content": TITLE_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.0,
        max_tokens=50,
    )
    if not cevap.choices or not cevap.choices[0].message.content:
        return ""
    raw = cevap.choices[0].message.content.strip()
    # İlk satır olsun, gereksiz prefix temizliği
    raw = raw.split("\n")[0].strip()
    for prefix in ("Başlık:", "Title:", "**", "-", "*"):
        if raw.startswith(prefix):
            raw = raw[len(prefix):].strip()
    raw = raw.strip("*: \"'")
    return raw


def main():
    # Maddeler
    print(f"Maddeler yükleniyor: {JSON_PATH}")
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        maddeler = json.load(f)
    print(f"Toplam {len(maddeler)} madde\n")

    # Mevcut başlıklar (resume desteği)
    basliklar: dict[str, str] = {}
    if Path(OUTPUT_PATH).exists():
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            basliklar = json.load(f)
        print(f"Mevcut {len(basliklar)} başlık bulundu, kaldığın yerden devam.")
    else:
        print("Sıfırdan başlıyor.")

    # LM Studio bağlantısı
    print(f"LM Studio: {LM_STUDIO_BASE_URL} ({LM_MODEL_NAME})")
    client = OpenAI(base_url=LM_STUDIO_BASE_URL, api_key=LM_STUDIO_API_KEY)

    # İşleme
    t0 = time.time()
    yapilan_yeni = 0
    for i, madde in enumerate(maddeler, start=1):
        key = str(madde["madde_no"])
        if key in basliklar and basliklar[key]:
            continue  # zaten yapılmış, atla

        icerik = madde["icerik"]
        try:
            baslik = title_for(client, madde["madde_no"], icerik)
        except Exception as e:
            print(f"  [HATA] Madde {key}: {e}")
            baslik = ""

        basliklar[key] = baslik
        yapilan_yeni += 1
        elapsed = time.time() - t0
        ortalama = elapsed / yapilan_yeni
        kalan = len(maddeler) - len([k for k in basliklar if basliklar[k]])
        eta_dk = (kalan * ortalama) / 60
        print(f"  [{i:3d}/{len(maddeler)}] Madde {key}: {baslik!r}  (ETA: {eta_dk:.1f} dk)")

        # Her 10 maddede bir diske yaz (kayıp önleme)
        if yapilan_yeni % 10 == 0:
            with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
                json.dump(basliklar, f, ensure_ascii=False, indent=2)

    # Son kayıt
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(basliklar, f, ensure_ascii=False, indent=2)

    bos = [k for k, v in basliklar.items() if not v]
    print(f"\n{'='*50}")
    print(f"Tamamlandı. Toplam başlık: {len(basliklar)}/{len(maddeler)}")
    if bos:
        print(f"Boş kalan {len(bos)} madde: {bos[:10]}{'...' if len(bos) > 10 else ''}")
    else:
        print("Tüm başlıklar üretildi.")
    print(f"Çıktı: {OUTPUT_PATH}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
